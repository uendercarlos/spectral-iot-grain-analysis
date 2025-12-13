# 🌾 Sistema Espectral IoT para Análise de Grãos

**Sistema de baixo custo para classificação não destrutiva de grãos usando espectroscopia VIS-NIR e Machine Learning**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Arduino](https://img.shields.io/badge/Arduino-ESP32-green.svg)](https://www.espressif.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![DOI](https://img.shields.io/badge/DOI-Dissertação-orange.svg)](#citação)

---

## 📋 Sumário

- [Visão Geral](#-visão-geral)
- [Arquitetura do Sistema](#-arquitetura-do-sistema)
- [Hardware Necessário](#-hardware-necessário)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Instalação](#-instalação)
- [Uso](#-uso)
- [Dataset](#-dataset)
- [Modelo de Machine Learning](#-modelo-de-machine-learning)
- [Resultados](#-resultados)
- [API Endpoints](#-api-endpoints)
- [Citação](#-citação)
- [Licença](#-licença)
- [Autores](#-autores)

---

## 🔬 Visão Geral

Este repositório contém o código-fonte completo do sistema espectral IoT desenvolvido como parte da dissertação de mestrado:

> **"Sistema Espectral IoT de Baixo Custo para Análise Não Destrutiva de Grãos com Machine Learning"**  
> Programa de Pós-Graduação em Tecnologia de Alimentos  
> Instituto Federal Goiano – Campus Rio Verde  
> Dezembro de 2025

O sistema integra:
- **Sensor multiespectral AS7265X** (18 bandas: 410-940 nm)
- **Microcontrolador ESP32** para aquisição e transmissão Wi-Fi
- **Servidor Flask** para processamento e inferência ML
- **Interface Web** para visualização em tempo real

### Principais Características

✅ Classificação de 4 espécies de grãos (soja, sorgo, milheto, grão-de-bico)  
✅ Acurácia de **97.9%** com validação Leave-One-Subject-Out (LOSO)  
✅ Detecção de anomalias híbrida (One-Class SVM + MAD)  
✅ Latência operacional de **~7 segundos**  
✅ Custo de hardware **< US$ 50**

---

## 🏗 Arquitetura do Sistema

```
┌─────────────────┐     I²C      ┌─────────────────┐
│    AS7265X      │─────────────▶│      ESP32      │
│  18 bandas      │              │  Pré-processamento
│  410-940 nm     │              │  Calibração     │
└─────────────────┘              └────────┬────────┘
                                          │ HTTP POST
                                          │ (Wi-Fi)
                                          ▼
┌─────────────────┐     HTTP     ┌─────────────────┐
│   Dashboard     │◀────────────▶│  Flask Server   │
│   Web (HTML5)   │              │  ML + API       │
└─────────────────┘              └────────┬────────┘
                                          │
        ┌─────────────────────────────────┘
        ▼
┌─────────────────┐
│  OLED SSD1306   │
│  Display Local  │
└─────────────────┘
```

**Fluxo de operação:**
1. Sensor AS7265X realiza aquisição espectral (18 bandas)
2. ESP32 aplica calibração dark-white e transmite via Wi-Fi
3. Servidor Flask remove banda instável (485 nm), calcula índices espectrais
4. Modelo SVM classifica espécie e detecta anomalias
5. Resultado exibido no display OLED e dashboard web

---

## 🔧 Hardware Necessário

| Componente | Modelo | Função |
|------------|--------|--------|
| Microcontrolador | ESP32-WROOM-32 | Controle e comunicação Wi-Fi |
| Sensor Espectral | SparkFun AS7265X Triad | 18 bandas (UV + VIS + NIR) |
| Display | OLED SSD1306 128x64 | Exibição local de resultados |
| Cone Óptico | PLA preto fosco (impressão 3D) | Isolamento luminoso |

**Conexões I²C:**
- AS7265X: SDA=GPIO21, SCL=GPIO22
- OLED: SDA=GPIO4, SCL=GPIO5

---

## 📁 Estrutura do Repositório

```
spectral-iot-grain-analysis/
│
├── firmware/                          # Código Arduino/ESP32
│   ├── coleta_dados_espectrais_18faixas_4.ino    # Coleta de dados para treinamento
│   └── inferencia_espectral_um_modelo_pkl.ino    # Inferência em tempo real
│
├── server/                            # Aplicação Flask
│   └── app_um_modelo_3.py             # Servidor de inferência com API REST
│
├── training/                          # Notebooks de treinamento
│   └── dissertacao_espectral_simples_um_modelo_6.ipynb  # Treinamento SVM + PCA
│
├── models/                            # Modelos serializados
│   └── modelo_completo_sem_485nm.pkl  # Modelo de produção (~9 MB)
│
├── data/                              # Datasets
│   └── tabela_coleta_dados_espectrais_4_amostras.csv  # 48 amostras (4 espécies)
│
├── docs/                              # Documentação adicional
│   └── AS7265x_Datasheet.pdf          # Datasheet do sensor
│
├── README.md                          # Este arquivo
├── requirements.txt                   # Dependências Python
└── LICENSE                            # Licença MIT
```

---

## 💻 Instalação

### Pré-requisitos

- Python 3.8+
- Arduino IDE 2.x
- Bibliotecas Arduino: SparkFun_AS7265X, Adafruit_SSD1306, ArduinoJson

### Servidor Flask

```bash
# Clonar repositório
git clone https://github.com/[seu-usuario]/spectral-iot-grain-analysis.git
cd spectral-iot-grain-analysis

# Criar ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt
```

**requirements.txt:**
```
flask>=2.0.0
flask-cors>=3.0.0
numpy>=1.21.0
pandas>=1.3.0
scikit-learn>=1.0.0
joblib>=1.1.0
```

### Firmware ESP32

1. Abrir Arduino IDE
2. Instalar bibliotecas via Library Manager:
   - `SparkFun AS7265X`
   - `Adafruit SSD1306`
   - `Adafruit GFX`
   - `ArduinoJson`
3. Selecionar placa: "ESP32 Dev Module"
4. Configurar Wi-Fi e IP do servidor no código
5. Fazer upload do firmware

---

## 🚀 Uso

### 1. Iniciar Servidor Flask

```bash
cd server
python app_um_modelo_3.py
```

O servidor inicia em `http://0.0.0.0:5000`

### 2. Configurar ESP32

Editar credenciais no firmware:
```cpp
const char* ssid = "SUA_REDE_WIFI";
const char* password = "SUA_SENHA";
const char* serverUrl = "http://IP_DO_SERVIDOR:5000";
```

### 3. Protocolo de Calibração

Antes de iniciar medições:
```
1. Comando 'dark'  → Recipiente vazio com fundo preto
2. Comando 'white' → Superfície branca de referência
3. Comando 'measure <grão>' → Iniciar coleta
```

### 4. Realizar Inferência

- Posicionar ~12g de grãos no recipiente
- Via interface web: clicar em "Analisar"
- Via API: `POST /command/analyze`
- Resultado exibido em ~7 segundos

---

## 📊 Dataset

O dataset contém **48 espectros** de 4 espécies de grãos:

| Espécie | Amostras | Repetições | Total |
|---------|----------|------------|-------|
| Soja | 4 | 3 | 12 |
| Grão-de-bico | 4 | 3 | 12 |
| Milheto | 4 | 3 | 12 |
| Sorgo | 4 | 3 | 12 |

**Bandas espectrais (nm):**
```
410, 435, 460, 485*, 510, 535, 560, 585, 610, 
645, 680, 705, 730, 760, 810, 860, 900, 940

* Banda 485 nm removida por instabilidade (CV% > 100%)
```

---

## 🤖 Modelo de Machine Learning

### Pipeline de Processamento

```
Espectro Bruto (18 bandas)
         │
         ▼
Remoção banda 485 nm (17 bandas)
         │
         ▼
Cálculo de Índices Espectrais
  • I1_NDVI = (r810 - r680) / (r810 + r680)
  • I2_Water = r940 / r760
  • I3_Lipid = r860 / r680
  • I4_Slope_Alt = (r645 - r535) / 110
         │
         ▼
PCA (6 componentes principais)
         │
         ▼
SVM Linear (classificação)
         │
         ▼
Detecção de Anomalias
  • One-Class SVM (por espécie)
  • MAD (Median Absolute Deviation)
  • Lógica AND (conservadora)
```

### Métricas de Desempenho

| Métrica | Valor |
|---------|-------|
| Acurácia (LOSO) | 97.9% |
| Variância Explicada (PCA) | 93.9% |
| Taxa de Falsos Positivos | ~0% |
| Latência Total | ~7 segundos |

---

## 📡 API Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/esp32/poll` | ESP32 verifica comandos pendentes |
| POST | `/esp32/result` | ESP32 envia espectro (18 bandas) |
| POST | `/command/analyze` | Solicita nova análise |
| GET | `/devices` | Lista dispositivos conectados |
| GET | `/last_analysis` | Retorna última análise |
| GET | `/history` | Histórico de análises |
| GET | `/status` | Status do sistema |
| GET | `/config` | Configuração atual |
| GET | `/export` | Exportar histórico (CSV) |

### Exemplo de Requisição

```bash
# Solicitar análise
curl -X POST http://localhost:5000/command/analyze \
  -H "Content-Type: application/json" \
  -d '{"device_id": "ESP32_001"}'

# Verificar última análise
curl http://localhost:5000/last_analysis
```

### Exemplo de Resposta

```json
{
  "especie": "soja",
  "confianca": 98.5,
  "status": "NORMAL",
  "indices": {
    "I1_NDVI": 0.0856,
    "I2_Water": 1.0412,
    "I3_Lipid": 0.9876,
    "I4_Slope_Alt": 0.0023
  },
  "timestamp": "2025-12-13T10:30:45.123456"
}
```

---

## 📈 Resultados

### Validação LOSO

A validação Leave-One-Subject-Out utilizou 16 folds (4 amostras × 4 espécies), onde cada fold exclui todas as repetições de uma amostra específica:

- **Acurácia média:** 97.9% (±2.1%)
- **Sem overfitting:** validação considera variabilidade inter-amostral

### Detecção de Anomalias

O sistema detectou com sucesso:
- ✅ Soja com alto teor de umidade (15-19% vs padrão 11-14%)
- ✅ Milheto contaminado com milho (mistura binária)
- ✅ Amostras com deriva espectral instrumental

---

## 📖 Citação

Se utilizar este código em sua pesquisa, por favor cite:

```bibtex
@mastersthesis{barbosa2025spectral,
  title={Sistema Espectral IoT de Baixo Custo para Análise Não Destrutiva de Grãos com Machine Learning},
  author={Barbosa, Uender Carlos},
  year={2025},
  school={Instituto Federal Goiano - Campus Rio Verde},
  type={Dissertação de Mestrado},
  program={Programa de Pós-Graduação em Tecnologia de Alimentos}
}
```

---

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

## 👥 Autores

**Mestrando:**
- Uender Carlos Barbosa

**Orientador:**
- Dr. Osvaldo Resende

**Coorientadores:**
- Dr. Daniel Emanuel Cabral de Oliveira
- Me. Leandro Rodrigues da Silva Souza
- Dra. Jaqueline Ferreira Vieira Bessa
- Dra. Juliana Aparecida Célia

---

## 🙏 Agradecimentos

- Instituto Federal Goiano – Campus Rio Verde
- Programa de Pós-Graduação em Tecnologia de Alimentos
- CAPES/CNPq pelo apoio financeiro

---

## 📬 Contato

Para dúvidas ou colaborações:
- **Email:** u.carlos3@gmail.com


---

<p align="center">
  <b>Desenvolvido com 🌱 para a Agricultura 4.0</b>
</p>
# spectral-iot-grain-analysis
