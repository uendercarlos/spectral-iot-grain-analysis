/**
 * ESP32 - INFERÊNCIA ALINHADA COM COLETA ORIGINAL
 * Mantém EXATAMENTE o mesmo processo da coleta de dados
 * 
 * Hardware:
 * - ESP32
 * - AS7265X (I2C: SDA=21, SCL=22)
 * - OLED 128x64 (I2C: SDA=4, SCL=5)
 * 
 * CRÍTICO: Usar mesmos valores de calibração da coleta!
 * Criado por Uender Carlos Barbosa - Email: u.carlos3@gmail.com
 */

#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <SparkFun_AS7265X.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

// ==================== CONFIGURAÇÕES ====================

// WiFi
const char* ssid = "nome_rede_wifi";
const char* password = "sua_senha";

// Servidor Flask
const char* serverUrl = "http://seu_ip_do_servidor_flask:5000";
const char* pollEndpoint = "/esp32/poll";
const char* resultEndpoint = "/esp32/result";

// Sensor AS7265X
AS7265X sensor;
#define SENSOR_SDA 21
#define SENSOR_SCL 22

// Display OLED
#define SDA_OLED 4
#define SCL_OLED 5
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire1, OLED_RESET);

// ==================== CALIBRAÇÃO ====================
// VALORES OBTIDOS NA CALIBRAÇÃO RECENTE (MESMOS DA COLETA!)

float darkCalibration[18] = {
  0.00, 1.93, 24.00, 6.09, 2.31, 0.00, 0.00, 0.00, 0.00, 
  0.35, 0.20, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00
};

float whiteCalibration[18] = {
  533.58, 401.11, 956.50, 266.51, 380.24, 386.41, 202.00, 214.65, 572.10, 
  113.14, 152.58, 35.57, 39.72, 29.51, 86.48, 309.36, 21.67, 21.69
};

// ==================== VARIÁVEIS GLOBAIS ====================

enum SystemState {
  STATE_WAITING,
  STATE_COLLECTING,
  STATE_PROCESSING,
  STATE_DISPLAYING
};

SystemState currentState = STATE_WAITING;

const int WARMUP_TIME = 5000;  // MESMO DA COLETA
String deviceId = "";

// Dados espectrais calibrados (DECLARAR AQUI!)
float spectralData[18];

// Resultado da análise
String lastEspecie = "";
float lastConfianca = 0;
String lastStatus = "";

// Controle de tempo
unsigned long lastPoll = 0;
const unsigned long POLL_INTERVAL = 2000;

// ==================== SETUP ====================

void setup() {
  Serial.begin(115200);
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║  CLASSIFICADOR DE GRÃOS - ESP32       ║");
  Serial.println("║  Inferência Alinhada com Coleta       ║");
  Serial.println("╚════════════════════════════════════════╝");
  
  deviceId = WiFi.macAddress();
  deviceId.replace(":", "");
  
  // Inicializar I2C para sensor
  Wire.begin(SENSOR_SDA, SENSOR_SCL);
  delay(500);
  
  // Inicializar sensor
  Serial.print("🔧 Inicializando sensor AS7265X...");
  if (!sensor.begin()) {
    Serial.println(" ERRO!");
    while (1) delay(1000);
  }
  Serial.println(" OK!");
  
  // MESMAS CONFIGURAÇÕES DA COLETA
  sensor.setMeasurementMode(AS7265X_MEASUREMENT_MODE_6CHAN_ONE_SHOT);
  sensor.setGain(AS7265X_GAIN_64X);
  sensor.setIntegrationCycles(49);  // ~280ms (IGUAL COLETA)
  sensor.setBulbCurrent(AS7265X_LED_CURRENT_LIMIT_12_5MA, AS7265x_LED_WHITE);
  sensor.setBulbCurrent(AS7265X_LED_CURRENT_LIMIT_12_5MA, AS7265x_LED_IR);
  sensor.setBulbCurrent(AS7265X_LED_CURRENT_LIMIT_12_5MA, AS7265x_LED_UV);
  
  Serial.println("✓ Sensor configurado (Ganho: 64X, Integração: 49 ciclos)");
  
  // Inicializar display OLED
  Wire1.begin(SDA_OLED, SCL_OLED);
  Serial.print("🖥️  Inicializando display OLED...");
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C, false, false)) {
    Serial.println(" ERRO!");
  } else {
    Serial.println(" OK!");
    display.setRotation(0);
    displayWaiting();
  }
  
  // Conectar WiFi
  WiFi.begin(ssid, password);
  Serial.print("📡 Conectando ao WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("✓ WiFi conectado!");
  Serial.print("📍 IP: ");
  Serial.println(WiFi.localIP());
  
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║  SISTEMA PRONTO                       ║");
  Serial.println("║  Aguardando comandos do Flask...      ║");
  Serial.println("╚════════════════════════════════════════╝\n");
}

// ==================== LOOP PRINCIPAL ====================

void loop() {
  // Verificar comandos do servidor periodicamente
  if (millis() - lastPoll > POLL_INTERVAL) {
    checkForCommands();
    lastPoll = millis();
  }
  
  // Máquina de estados
  switch (currentState) {
    case STATE_WAITING:
      break;
      
    case STATE_COLLECTING:
      collectSpectralData();
      break;
      
    case STATE_PROCESSING:
      sendResultsToServer();
      break;
      
    case STATE_DISPLAYING:
      displayResults();
      delay(5000);
      currentState = STATE_WAITING;
      displayWaiting();
      break;
  }
  
  delay(100);
}

// ==================== COMUNICAÇÃO COM SERVIDOR ====================

void checkForCommands() {
  if (WiFi.status() != WL_CONNECTED) return;
  
  HTTPClient http;
  http.begin(String(serverUrl) + String(pollEndpoint));
  http.addHeader("Content-Type", "application/json");
  
  DynamicJsonDocument requestDoc(512);
  requestDoc["device_id"] = deviceId;
  requestDoc["status"] = getStateString();
  requestDoc["ip"] = WiFi.localIP().toString();
  
  String requestBody;
  serializeJson(requestDoc, requestBody);
  
  int httpResponseCode = http.POST(requestBody);
  
  if (httpResponseCode == 200) {
    String response = http.getString();
    
    DynamicJsonDocument responseDoc(1024);
    deserializeJson(responseDoc, response);
    
    if (responseDoc.containsKey("command")) {
      String command = responseDoc["command"];
      
      if (command == "analyze") {
        Serial.println("📋 Comando recebido: Analisar grão");
        currentState = STATE_COLLECTING;
      }
    }
  }
  
  http.end();
}

void sendResultsToServer() {
  if (WiFi.status() != WL_CONNECTED) {
    currentState = STATE_DISPLAYING;
    return;
  }
  
  Serial.println("📤 Enviando espectro ao servidor...");
  
  HTTPClient http;
  http.begin(String(serverUrl) + String(resultEndpoint));
  http.addHeader("Content-Type", "application/json");
  
  DynamicJsonDocument doc(2048);
  doc["device_id"] = deviceId;
  
  // CRIAR ARRAY COM VALORES DE REFLECTÂNCIA (0-1)
  JsonArray spectrum = doc.createNestedArray("spectrum");
  for (int i = 0; i < 18; i++) {
    spectrum.add(spectralData[i]);
  }
  
  String requestBody;
  serializeJson(doc, requestBody);
  
  Serial.println("📋 JSON enviado:");
  Serial.println(requestBody);
  
  int httpResponseCode = http.POST(requestBody);
  
  if (httpResponseCode == 200) {
    String response = http.getString();
    Serial.println("✓ Resposta recebida:");
    Serial.println(response);
    
    DynamicJsonDocument responseDoc(1024);
    deserializeJson(responseDoc, response);
    
    lastEspecie = responseDoc["especie"].as<String>();
    lastConfianca = responseDoc["confianca"];
    lastStatus = responseDoc["status"].as<String>();
    
    currentState = STATE_DISPLAYING;
  } else {
    Serial.printf("❌ Erro no envio: %d\n", httpResponseCode);
    lastEspecie = "ERRO";
    lastStatus = "ERRO_CONEXAO";
    lastConfianca = 0;
    currentState = STATE_DISPLAYING;
  }
  
  http.end();
}

// ==================== COLETA ESPECTRAL ====================

void collectSpectralData() {
  Serial.println("\n📊 Coletando dados espectrais...");
  displayMessage("Analisando", "Aguarde...");
  
  // Habilitar LEDs (MESMO DA COLETA)
  sensor.enableBulb(AS7265x_LED_WHITE);
  sensor.enableBulb(AS7265x_LED_IR);
  sensor.enableBulb(AS7265x_LED_UV);
  
  Serial.println("⏳ Aquecendo LEDs...");
  delay(WARMUP_TIME);  // 5000ms (MESMO DA COLETA)
  
  Serial.println("📡 Coletando dados espectrais...");
  sensor.takeMeasurements();
  
  // Obter dados brutos (MESMA FUNÇÃO DA COLETA)
  float rawData[18];
  getSpectralData(rawData);
  
  // APLICAR CALIBRAÇÃO (MESMO PROCESSO DA COLETA)
  for (int i = 0; i < 18; i++) {
    float denominator = whiteCalibration[i] - darkCalibration[i];
    if (denominator > 0) {
      spectralData[i] = (rawData[i] - darkCalibration[i]) / denominator;
      spectralData[i] = constrain(spectralData[i], 0.0, 1.0);
    } else {
      spectralData[i] = 0;
    }
  }
  
  // Desabilitar LEDs
  sensor.disableBulb(AS7265x_LED_WHITE);
  sensor.disableBulb(AS7265x_LED_IR);
  sensor.disableBulb(AS7265x_LED_UV);
  
  Serial.println("✓ Medição concluída!");
  Serial.printf("  r680=%.6f, r810=%.6f, r940=%.6f\n", 
                spectralData[10], spectralData[14], spectralData[17]);
  
  currentState = STATE_PROCESSING;
}

// ORDEM DAS BANDAS - IDÊNTICA AO CÓDIGO DE COLETA
void getSpectralData(float* data) {
  // UV (410-535 nm)
  data[0] = sensor.getCalibratedA();  // 410
  data[1] = sensor.getCalibratedB();  // 435
  data[2] = sensor.getCalibratedC();  // 460
  data[3] = sensor.getCalibratedD();  // 485
  data[4] = sensor.getCalibratedE();  // 510
  data[5] = sensor.getCalibratedF();  // 535
  
  // VIS (560-705 nm)
  data[6] = sensor.getCalibratedG();   // 560
  data[7] = sensor.getCalibratedH();   // 585
  data[8] = sensor.getCalibratedR();   // 610  ← R
  data[9] = sensor.getCalibratedI();   // 645  ← I
  data[10] = sensor.getCalibratedS();  // 680  ← S
  data[11] = sensor.getCalibratedJ();  // 705  ← J
  
  // IR (730-940 nm)
  data[12] = sensor.getCalibratedT();  // 730  ← T
  data[13] = sensor.getCalibratedU();  // 760  ← U
  data[14] = sensor.getCalibratedV();  // 810  ← V
  data[15] = sensor.getCalibratedW();  // 860  ← W
  data[16] = sensor.getCalibratedK();  // 900  ← K
  data[17] = sensor.getCalibratedL();  // 940  ← L
}

// ==================== DISPLAY OLED ====================

void displayWaiting() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  
  display.setTextSize(2);
  display.setCursor(10, 5);
  display.println("AGUARDANDO");
  
  display.setTextSize(1);
  display.setCursor(15, 30);
  display.println("COMANDO FLASK");
  
  static int dots = 0;
  display.setCursor(50, 45);
  for (int i = 0; i < (dots % 4); i++) {
    display.print(".");
  }
  dots++;
  
  display.setCursor(0, 55);
  display.printf("IP:%s", WiFi.localIP().toString().c_str());
  
  display.display();
}

void displayMessage(String title, String message) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  
  display.setTextSize(2);
  display.setCursor(5, 10);
  display.println(title);
  
  display.setTextSize(1);
  display.setCursor(15, 35);
  display.println(message);
  
  display.display();
}

void displayResults() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  
  // Borda
  display.drawRect(0, 0, 128, 64, SSD1306_WHITE);
  
  // Espécie (grande)
  display.setTextSize(2);
  display.setCursor(10, 5);
  
  String especieTrunc = lastEspecie;
  if (lastEspecie.length() > 10) {
    especieTrunc = lastEspecie.substring(0, 10);
  }
  display.println(especieTrunc);
  
  // Confiança
  display.setTextSize(1);
  display.setCursor(5, 28);
  display.printf("Conf: %.1f%%", lastConfianca);
  
  // Status
  display.setCursor(5, 40);
  display.printf("Status: %s", lastStatus.c_str());
  
  // Indicador visual
  if (lastStatus == "NORMAL") {
    display.fillCircle(115, 45, 6, SSD1306_WHITE);
  } else {
    display.drawCircle(115, 45, 6, SSD1306_WHITE);
    display.drawLine(109, 39, 121, 51, SSD1306_WHITE);
    display.drawLine(109, 51, 121, 39, SSD1306_WHITE);
  }
  
  display.setCursor(5, 54);
  display.print("Aguardando...");
  
  display.display();
  
  // Imprimir no Serial
  Serial.println("\n╔════════════════════════════════════════╗");
  Serial.println("║       RESULTADO DA ANÁLISE            ║");
  Serial.println("╠════════════════════════════════════════╣");
  Serial.printf("║ Espécie:    %-23s║\n", lastEspecie.c_str());
  Serial.printf("║ Confiança:  %.1f%%                    ║\n", lastConfianca);
  Serial.printf("║ Status:     %-23s║\n", lastStatus.c_str());
  Serial.println("╚════════════════════════════════════════╝\n");
}

String getStateString() {
  switch (currentState) {
    case STATE_WAITING: return "waiting";
    case STATE_COLLECTING: return "collecting";
    case STATE_PROCESSING: return "processing";
    case STATE_DISPLAYING: return "displaying";
    default: return "unknown";
  }
}