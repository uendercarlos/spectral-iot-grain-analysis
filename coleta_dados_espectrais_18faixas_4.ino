/*
 * Sistema de Coleta Espectral para Dissertação de Mestrado
 * Hardware: ESP32 + Sensor AS7265X (UV + VIS + IR)
 * Protocolo: Calibração Dark/White + Medições Repetidas
 * 
 * Autor: Sistema IoT Espectral
 * Versão: 1.0 - Coleta para Análise Estatística e ML
 * Criado por Uender Carlos Barbosa - Email: u.carlos3@gmail.com
 */

#include <Wire.h>
#include "SparkFun_AS7265X.h"

// ========== CONFIGURAÇÕES GLOBAIS ==========
AS7265X sensor;

// Bandas espectrais em nanômetros (18 canais)
const int SPECTRAL_BANDS[18] = {
  410, 435, 460, 485, 510, 535, 560, 585, 610, 
  645, 680, 705, 730, 760, 810, 860, 900, 940
};

// Dados de calibração obtidos experimentalmente
float darkCalibration[18] = {
  0, 2, 1, 8, 1, 4, 2, 0, 0, 0, 0, 1, 0.8, 0, 0, 0, 0, 0
};

float whiteCalibration[18] = {
  191, 588, 33.4, 412, 442, 533.4, 432, 478.4, 467.2, 
  270, 136.2, 854, 324, 551, 811, 10, 0, 0
};

// Estado do sistema
enum SystemState {
  IDLE,
  CALIBRATING_DARK,
  CALIBRATING_WHITE,
  MEASURING
};

SystemState currentState = IDLE;

// Configurações de medição
const int MEASUREMENT_DELAY = 2000;  // 2 segundos entre leituras
const int WARMUP_TIME = 5000;        // 5 segundos de aquecimento
int measurementCount = 0;
int currentSample = 1;
int currentRepetition = 1;

// ========== SETUP ==========
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);
  
  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║  Sistema Espectral IoT - Coleta de Dados      ║");
  Serial.println("║  AS7265X (UV + VIS + IR) - 18 Bandas          ║");
  Serial.println("╚════════════════════════════════════════════════╝\n");

  // Inicializar sensor
  Wire.begin();
  
  if (!sensor.begin()) {
    Serial.println("❌ ERRO: Sensor AS7265X não detectado!");
    Serial.println("Verifique as conexões I2C (SDA=21, SCL=22)");
    while (1) delay(100);
  }
  
  Serial.println("✓ Sensor AS7265X inicializado com sucesso\n");
  
  // Configurar sensor para melhor precisão
  sensor.setMeasurementMode(AS7265X_MEASUREMENT_MODE_6CHAN_ONE_SHOT);
  sensor.setGain(AS7265X_GAIN_64X);           // Ganho máximo para sensibilidade
  sensor.setIntegrationCycles(49);            // ~280ms de integração
  sensor.setBulbCurrent(AS7265X_LED_CURRENT_LIMIT_12_5MA, AS7265x_LED_WHITE);
  sensor.setBulbCurrent(AS7265X_LED_CURRENT_LIMIT_12_5MA, AS7265x_LED_IR);
  sensor.setBulbCurrent(AS7265X_LED_CURRENT_LIMIT_12_5MA, AS7265x_LED_UV);
  
  // Desabilitar LEDs inicialmente
  sensor.disableBulb(AS7265x_LED_WHITE);
  sensor.disableBulb(AS7265x_LED_IR);
  sensor.disableBulb(AS7265x_LED_UV);
  
  displayMenu();
}

// ========== LOOP PRINCIPAL ==========
void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    command.toLowerCase();
    
    processCommand(command);
  }
  
  delay(100);
}

// ========== PROCESSAMENTO DE COMANDOS ==========
void processCommand(String cmd) {
  
  if (cmd == "help" || cmd == "?") {
    displayMenu();
  }
  else if (cmd == "reset") {
    resetSystem();
  }
  else if (cmd == "dark") {
    calibrateDark();
  }
  else if (cmd == "white") {
    calibrateWhite();
  }
  else if (cmd.startsWith("measure")) {
    startMeasurement(cmd);
  }
  else if (cmd == "show") {
    showCalibration();
  }
  else if (cmd == "status") {
    showStatus();
  }
  else {
    Serial.println("⚠ Comando não reconhecido. Digite 'help' para ajuda.");
  }
}

// ========== MENU DE AJUDA ==========
void displayMenu() {
  Serial.println("╔════════════════════════════════════════════════╗");
  Serial.println("║           COMANDOS DISPONÍVEIS                 ║");
  Serial.println("╠════════════════════════════════════════════════╣");
  Serial.println("║ reset          - Reinicializar sistema         ║");
  Serial.println("║ dark           - Calibração dark current       ║");
  Serial.println("║ white          - Calibração white reference    ║");
  Serial.println("║ measure <grão> - Iniciar medição espectral    ║");
  Serial.println("║                  Grãos: soja, grao-de-bico,    ║");
  Serial.println("║                         milheto, sorgo         ║");
  Serial.println("║ show           - Exibir dados de calibração    ║");
  Serial.println("║ status         - Status do sistema             ║");
  Serial.println("║ help           - Exibir este menu              ║");
  Serial.println("╚════════════════════════════════════════════════╝\n");
  
  Serial.println("📋 PROTOCOLO DE COLETA:");
  Serial.println("1. Executar calibração 'dark' (recipiente vazio/preto)");
  Serial.println("2. Executar calibração 'white' (superfície branca)");
  Serial.println("3. Posicionar amostra na mesma altura do sensor");
  Serial.println("4. Executar 'measure <tipo_grão>' para coletar");
  Serial.println("5. Agitar levemente entre repetições\n");
}

// ========== RESET DO SISTEMA ==========
void resetSystem() {
  Serial.println("\n🔄 Reinicializando sistema...");
  
  currentState = IDLE;
  measurementCount = 0;
  currentSample = 1;
  currentRepetition = 1;
  
  // Desabilitar todos os LEDs
  sensor.disableBulb(AS7265x_LED_WHITE);
  sensor.disableBulb(AS7265x_LED_IR);
  sensor.disableBulb(AS7265x_LED_UV);
  
  Serial.println("✓ Sistema reinicializado\n");
  displayMenu();
}

// ========== CALIBRAÇÃO DARK CURRENT ==========
void calibrateDark() {
  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║        CALIBRAÇÃO DARK CURRENT                 ║");
  Serial.println("╚════════════════════════════════════════════════╝");
  Serial.println("\n📌 INSTRUÇÕES:");
  Serial.println("• Certifique-se de que o recipiente está vazio");
  Serial.println("• Use fundo preto fosco");
  Serial.println("• Ausência total de luz externa");
  Serial.println("\nPressione ENTER para iniciar...");
  
  while (Serial.available() == 0) delay(10);
  while (Serial.available() > 0) Serial.read();
  
  Serial.println("\n⏳ Coletando dark current...");
  
  // Desabilitar todos os LEDs
  sensor.disableBulb(AS7265x_LED_WHITE);
  sensor.disableBulb(AS7265x_LED_IR);
  sensor.disableBulb(AS7265x_LED_UV);
  
  delay(WARMUP_TIME);
  
  // Realizar 5 medições e calcular média
  float darkSum[18] = {0};
  const int NUM_DARK_READS = 5;
  
  for (int i = 0; i < NUM_DARK_READS; i++) {
    sensor.takeMeasurements();
    
    float readings[18];
    getSpectralData(readings);
    
    for (int j = 0; j < 18; j++) {
      darkSum[j] += readings[j];
    }
    
    Serial.print(".");
    delay(500);
  }
  
  Serial.println(" OK");
  
  // Calcular média
  for (int i = 0; i < 18; i++) {
    darkCalibration[i] = darkSum[i] / NUM_DARK_READS;
  }
  
  Serial.println("\n✓ Calibração dark concluída!");
  Serial.println("\n📊 Valores obtidos (dark current):");
  printSpectralArray(darkCalibration);
  
  currentState = CALIBRATING_DARK;
}

// ========== CALIBRAÇÃO WHITE REFERENCE ==========
void calibrateWhite() {
  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║        CALIBRAÇÃO WHITE REFERENCE              ║");
  Serial.println("╚════════════════════════════════════════════════╝");
  Serial.println("\n📌 INSTRUÇÕES:");
  Serial.println("• Posicionar superfície branca de referência");
  Serial.println("• Mesma altura das futuras amostras");
  Serial.println("• Iluminação estável");
  Serial.println("\nPressione ENTER para iniciar...");
  
  while (Serial.available() == 0) delay(10);
  while (Serial.available() > 0) Serial.read();
  
  Serial.println("\n⏳ Coletando white reference...");
  
  // Habilitar todos os LEDs
  sensor.enableBulb(AS7265x_LED_WHITE);
  sensor.enableBulb(AS7265x_LED_IR);
  sensor.enableBulb(AS7265x_LED_UV);
  
  delay(WARMUP_TIME);
  
  // Realizar 5 medições e calcular média
  float whiteSum[18] = {0};
  const int NUM_WHITE_READS = 5;
  
  for (int i = 0; i < NUM_WHITE_READS; i++) {
    sensor.takeMeasurements();
    
    float readings[18];
    getSpectralData(readings);
    
    for (int j = 0; j < 18; j++) {
      whiteSum[j] += readings[j];
    }
    
    Serial.print(".");
    delay(500);
  }
  
  Serial.println(" OK");
  
  // Calcular média
  for (int i = 0; i < 18; i++) {
    whiteCalibration[i] = whiteSum[i] / NUM_WHITE_READS;
  }
  
  // Desabilitar LEDs
  sensor.disableBulb(AS7265x_LED_WHITE);
  sensor.disableBulb(AS7265x_LED_IR);
  sensor.disableBulb(AS7265x_LED_UV);
  
  Serial.println("\n✓ Calibração white concluída!");
  Serial.println("\n📊 Valores obtidos (white reference):");
  printSpectralArray(whiteCalibration);
  
  currentState = CALIBRATING_WHITE;
}

// ========== MEDIÇÃO ESPECTRAL ==========
void startMeasurement(String cmd) {
  // Extrair tipo de grão do comando
  String grainType = "";
  int spacePos = cmd.indexOf(' ');
  
  if (spacePos > 0) {
    grainType = cmd.substring(spacePos + 1);
    grainType.trim();
  }
  
  // Validar tipo de grão
  if (grainType != "soja" && grainType != "grao-de-bico" && 
      grainType != "milheto" && grainType != "sorgo") {
    Serial.println("\n⚠ Erro: Tipo de grão inválido!");
    Serial.println("Opções válidas: soja, grao-de-bico, milheto, sorgo");
    return;
  }
  
  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║          COLETA DE DADOS ESPECTRAIS            ║");
  Serial.println("╚════════════════════════════════════════════════╝");
  Serial.printf("\n🌾 Grão: %s\n", grainType.c_str());
  Serial.printf("📦 Amostra: %d\n", currentSample);
  Serial.printf("🔁 Repetição: %d de 3\n\n", currentRepetition);
  
  Serial.println("📌 INSTRUÇÕES:");
  Serial.println("• Certifique-se de que a amostra está posicionada");
  Serial.println("• Mesma altura do sensor");
  Serial.println("• Grãos distribuídos uniformemente");
  Serial.println("\nPressione ENTER para medir...");
  
  while (Serial.available() == 0) delay(10);
  while (Serial.available() > 0) Serial.read();
  
  // Habilitar LEDs
  sensor.enableBulb(AS7265x_LED_WHITE);
  sensor.enableBulb(AS7265x_LED_IR);
  sensor.enableBulb(AS7265x_LED_UV);
  
  Serial.println("\n⏳ Aquecendo LEDs...");
  delay(WARMUP_TIME);
  
  Serial.println("📡 Coletando dados espectrais...");
  sensor.takeMeasurements();
  
  // Obter dados brutos
  float rawData[18];
  getSpectralData(rawData);
  
  // Aplicar calibração (reflectância relativa)
  float calibratedData[18];
  for (int i = 0; i < 18; i++) {
    float denominator = whiteCalibration[i] - darkCalibration[i];
    if (denominator > 0) {
      calibratedData[i] = (rawData[i] - darkCalibration[i]) / denominator;
      calibratedData[i] = constrain(calibratedData[i], 0.0, 1.0);
    } else {
      calibratedData[i] = 0;
    }
  }
  
  // Desabilitar LEDs
  sensor.disableBulb(AS7265x_LED_WHITE);
  sensor.disableBulb(AS7265x_LED_IR);
  sensor.disableBulb(AS7265x_LED_UV);
  
  Serial.println("✓ Medição concluída!\n");
  
  // Exibir dados em formato CSV para cópia
  Serial.println("╔════════════════════════════════════════════════╗");
  Serial.println("║          DADOS PARA ANÁLISE (CSV)              ║");
  Serial.println("╚════════════════════════════════════════════════╝\n");
  
  // Cabeçalho CSV (só na primeira medição)
  if (measurementCount == 0) {
    Serial.print("sample,grain,repetition");
    for (int i = 0; i < 18; i++) {
      Serial.printf(",band_%d", SPECTRAL_BANDS[i]);
    }
    Serial.println();
  }
  
  // Linha de dados
  Serial.printf("%d,%s,%d", currentSample, grainType.c_str(), currentRepetition);
  for (int i = 0; i < 18; i++) {
    Serial.printf(",%.6f", calibratedData[i]);
  }
  Serial.println();
  
  measurementCount++;
  
  // Controlar repetições e amostras
  currentRepetition++;
  if (currentRepetition > 3) {
    currentRepetition = 1;
    currentSample++;
    
    Serial.println("\n✓ 3 repetições da amostra concluídas!");
    if (currentSample <= 4) {
      Serial.printf("\n➡ Próxima: Amostra %d\n", currentSample);
      Serial.println("Substitua a amostra e execute 'measure' novamente.\n");
    } else {
      Serial.println("\n🎉 Todas as 4 amostras coletadas!");
      Serial.println("Total de medições: 12 (4 amostras × 3 repetições)\n");
      currentSample = 1;
    }
  } else {
    Serial.printf("\n➡ Próxima: Repetição %d\n", currentRepetition);
    Serial.println("Agite levemente a amostra e execute 'measure' novamente.\n");
  }
}

// ========== OBTER DADOS ESPECTRAIS ==========
void getSpectralData(float* data) {
  // UV (410-460 nm)
  data[0] = sensor.getCalibratedA();  // 410
  data[1] = sensor.getCalibratedB();  // 435
  data[2] = sensor.getCalibratedC();  // 460
  data[3] = sensor.getCalibratedD();  // 485
  data[4] = sensor.getCalibratedE();  // 510
  data[5] = sensor.getCalibratedF();  // 535
  
  // VIS (560-680 nm)
  data[6] = sensor.getCalibratedG();   // 560
  data[7] = sensor.getCalibratedH();   // 585
  data[8] = sensor.getCalibratedR();   // 610
  data[9] = sensor.getCalibratedI();   // 645
  data[10] = sensor.getCalibratedS();  // 680
  data[11] = sensor.getCalibratedJ();  // 705
  
  // IR (730-940 nm)
  data[12] = sensor.getCalibratedT();  // 730
  data[13] = sensor.getCalibratedU();  // 760
  data[14] = sensor.getCalibratedV();  // 810
  data[15] = sensor.getCalibratedW();  // 860
  data[16] = sensor.getCalibratedK();  // 900
  data[17] = sensor.getCalibratedL();  // 940
}

// ========== EXIBIR ARRAY ESPECTRAL ==========
void printSpectralArray(float* data) {
  Serial.println("┌──────┬────────────┐");
  Serial.println("│  nm  │   Valor    │");
  Serial.println("├──────┼────────────┤");
  
  for (int i = 0; i < 18; i++) {
    Serial.printf("│ %4d │ %10.2f │\n", SPECTRAL_BANDS[i], data[i]);
  }
  
  Serial.println("└──────┴────────────┘\n");
}

// ========== MOSTRAR CALIBRAÇÃO ==========
void showCalibration() {
  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║         DADOS DE CALIBRAÇÃO ATUAIS             ║");
  Serial.println("╚════════════════════════════════════════════════╝\n");
  
  Serial.println("🌑 DARK CURRENT:");
  printSpectralArray(darkCalibration);
  
  Serial.println("⚪ WHITE REFERENCE:");
  printSpectralArray(whiteCalibration);
}

// ========== MOSTRAR STATUS ==========
void showStatus() {
  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║            STATUS DO SISTEMA                   ║");
  Serial.println("╚════════════════════════════════════════════════╝\n");
  
  Serial.print("Estado atual: ");
  switch (currentState) {
    case IDLE:
      Serial.println("IDLE - Aguardando calibração");
      break;
    case CALIBRATING_DARK:
      Serial.println("Dark calibrado - Necessário calibrar White");
      break;
    case CALIBRATING_WHITE:
      Serial.println("Sistema calibrado - Pronto para medições");
      break;
    case MEASURING:
      Serial.println("Em medição");
      break;
  }
  
  Serial.printf("Total de medições: %d\n", measurementCount);
  Serial.printf("Amostra atual: %d de 4\n", currentSample);
  Serial.printf("Repetição atual: %d de 3\n\n", currentRepetition);
  
  Serial.println("💡 Sensor AS7265X:");
  Serial.printf("• Ganho: 64X\n");
  Serial.printf("• Tempo de integração: ~280ms\n");
  Serial.printf("• Bandas espectrais: 18 (410-940 nm)\n\n");
}