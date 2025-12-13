"""
Flask - Servidor de Inferência para Classificação de Grãos
Versão Otimizada - Modelo SEM banda 485nm

AJUSTES APLICADOS (VERSÃO CORRIGIDA):
- Modelo sem banda 485nm (17 bandas)
- Índices espectrais novos: I1_NDVI, I2_Water, I3_Lipid, I4_Slope_Alt
- Recebe 18 bandas do ESP32 e remove r485 automaticamente
- Lógica de anomalia: AND (conservadora) + alerta de confiança baixa
- Violações MAD: >= 2 (ajustado para detectar contaminações)
- Alerta de confiança baixa: < 60%

CORREÇÕES DESTA VERSÃO:
- Reduzido limiar MAD de 3 para 2 violações (melhor detecção de contaminação)
- Adicionado alerta para confiança < 60% (detecta misturas)
- Mantém baixa taxa de falsos positivos com lógica AND

Instalação:
pip install flask flask-cors numpy pandas joblib scikit-learn

Uso:
python app_um_modelo_corrigido.py

Criado por Uender Carlos Barbosa - Email: u.carlos3@gmail.com

"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import pandas as pd
import joblib
import logging
from datetime import datetime
from collections import deque
import threading
import time

# ==================== CONFIGURAÇÃO ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'grain_classifier_2025'
CORS(app)

# ==================== VARIÁVEIS GLOBAIS ====================

DEVICE_TIMEOUT = 10
analysis_history = deque(maxlen=100)
connected_devices = {}
pending_commands = {}
last_analysis = None
analysis_lock = threading.Lock()

# Componentes do modelo
MODELOS = None
modelo_especies = None
detectores_anomalia = None
limiares_mad = None
scaler_bandas = None
scaler_indices = None
scaler_final = None
pca = None
bandas_cols = None
indices_cols = None


# ==================== CARREGAMENTO DO MODELO ====================

def carregar_modelo():
    """Carrega modelo treinado"""
    global MODELOS, modelo_especies, detectores_anomalia, limiares_mad
    global scaler_bandas, scaler_indices, scaler_final, pca, bandas_cols, indices_cols

    try:
        logger.info("📦 Carregando modelo_completo_sem_485nm.pkl...")

        MODELOS = joblib.load('modelo_completo_sem_485nm.pkl')

        modelo_especies = MODELOS['modelo_especies']
        detectores_anomalia = MODELOS['detectores_anomalia']
        limiares_mad = MODELOS['limiares_mad']
        scaler_bandas = MODELOS['scaler_bandas']
        scaler_indices = MODELOS['scaler_indices']
        scaler_final = MODELOS['scaler_final']
        pca = MODELOS['pca']
        bandas_cols = MODELOS['bandas_cols']
        indices_cols = MODELOS['indices_cols']

        logger.info("✅ Modelo carregado!")
        logger.info(f"🌾 Espécies: {modelo_especies.classes_}")
        logger.info(f"📊 Bandas no modelo: {len(bandas_cols)}")
        logger.info(f"📈 Índices: {list(indices_cols)}")
        logger.info(f"⚠️ IMPORTANTE: ESP32 envia 18 bandas, servidor remove r485 automaticamente")

        return True

    except FileNotFoundError:
        logger.error("❌ Arquivo 'modelo_completo_graos.pkl' não encontrado!")
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao carregar modelo: {e}")
        return False


# ==================== FUNÇÕES DE CÁLCULO ====================

def calcular_indices_novos(df):
    """
    Índices espectrais SEM usar banda 485nm
    Alinhados com modelo de produção
    """
    df = df.copy()
    df['I1_NDVI'] = (df['r810'] - df['r680']) / (df['r810'] + df['r680'] + 1e-10)
    df['I2_Water'] = df['r940'] / (df['r760'] + 1e-10)
    df['I3_Lipid'] = df['r860'] / (df['r680'] + 1e-10)
    df['I4_Slope_Alt'] = (df['r645'] - df['r535']) / 110.0
    return df


def remover_banda_485(spectrum_18_bandas):
    """
    Remove a banda 485nm (índice 3) do espectro de 18 bandas

    ESP32 envia 18 bandas na ordem:
    [410, 435, 460, 485, 510, 535, 560, 585, 610, 645, 680, 705, 730, 760, 810, 860, 900, 940]

    Retorna 17 bandas sem a r485:
    [410, 435, 460, 510, 535, 560, 585, 610, 645, 680, 705, 730, 760, 810, 860, 900, 940]
    """
    if len(spectrum_18_bandas) != 18:
        raise ValueError(f"Esperado 18 bandas, recebido {len(spectrum_18_bandas)}")

    # Remover índice 3 (banda 485nm)
    spectrum_17_bandas = spectrum_18_bandas[:3] + spectrum_18_bandas[4:]

    logger.info(f"✂️ Banda 485nm removida: {spectrum_18_bandas[3]:.6f}")

    return spectrum_17_bandas


def prever_amostra(spectrum_18_bandas):
    """
    Função de inferência principal
    RECEBE 18 bandas do ESP32 e remove r485 antes da predição
    USA ÍNDICES NOVOS: I1_NDVI, I2_Water, I3_Lipid, I4_Slope_Alt

    AJUSTES DE ANOMALIA (VERSÃO CORRIGIDA):
    - Lógica AND em vez de OR (mais conservadora)
    - Violações MAD >= 2 (ajustado de 3 para melhor detecção)
    - Alerta de confiança < 60% (detecta misturas/contaminações)
    """
    try:
        # VALIDAR ENTRADA DE 18 BANDAS
        if len(spectrum_18_bandas) != 18:
            raise ValueError(f"Espectro inválido: {len(spectrum_18_bandas)} bandas (esperado: 18)")

        # REMOVER BANDA 485nm (índice 3)
        spectrum = remover_banda_485(spectrum_18_bandas)

        # Agora temos 17 bandas para o modelo
        if len(spectrum) != len(bandas_cols):
            raise ValueError(f"Erro: {len(spectrum)} bandas após remoção, modelo espera {len(bandas_cols)}")

        # 1. Criar DataFrame com bandas (MESMA ORDEM DO TREINAMENTO)
        bandas_dict = {bandas_cols[i]: spectrum[i] for i in range(len(bandas_cols))}
        df_temp = pd.DataFrame([bandas_dict])

        # 2. Calcular índices espectrais NOVOS
        df_temp = calcular_indices_novos(df_temp)
        indices_array = df_temp[indices_cols].values

        # LOG dos índices calculados
        logger.info(f"📊 Índices calculados:")
        for idx_name, idx_value in zip(indices_cols, indices_array[0]):
            logger.info(f"   {idx_name}: {idx_value:.4f}")

        # 3. Processar bandas com PCA
        bandas_array = np.array(spectrum).reshape(1, -1)
        bandas_scaled = scaler_bandas.transform(bandas_array)
        pca_array = pca.transform(bandas_scaled)

        # 4. Combinar features (4 índices + 6 PCs)
        X_completo = np.hstack([indices_array, pca_array[:, :6]])
        X_completo_scaled = scaler_final.transform(X_completo)

        # 5. Predição de espécie
        especie_pred = modelo_especies.predict(X_completo_scaled)[0]
        prob_especies = modelo_especies.predict_proba(X_completo_scaled)[0]
        confianca = float(np.max(prob_especies))

        logger.info(f"🎯 Espécie predita: {especie_pred} ({confianca * 100:.1f}%)")

        # 6. Detecção de anomalia (LÓGICA AJUSTADA)
        indices_scaled = scaler_indices.transform(indices_array)

        # One-Class SVM
        decisao_svm = detectores_anomalia[especie_pred].predict(indices_scaled)[0]
        score_svm = detectores_anomalia[especie_pred].decision_function(indices_scaled)[0]
        anomalia_svm = (decisao_svm == -1)

        logger.info(f"🔍 One-Class SVM: decisão={decisao_svm}, score={score_svm:.4f}")

        # Regra MAD (AJUSTADA: >= 2 violações para maior sensibilidade)
        limiar = limiares_mad[especie_pred]
        desvios = np.abs(indices_scaled[0] - limiar['medians'])
        violacoes = np.sum(desvios > limiar['mads'])
        anomalia_mad = (violacoes >= 2)  # ← MUDOU DE 3 PARA 2

        logger.info(f"🔍 Regra MAD: violações={violacoes}/4, limiar=2")

        # Log detalhado das violações
        for i, (idx_name, desvio, mad) in enumerate(zip(indices_cols, desvios, limiar['mads'])):
            violou = "❌ VIOLOU" if desvio > mad else "✅ OK"
            logger.info(f"   {idx_name}: desvio={desvio:.4f}, limiar={mad:.4f} {violou}")

        # Status final (LÓGICA AND: ambos devem concordar)
        status = "ANORMAL" if (anomalia_svm and anomalia_mad) else "NORMAL"

        # ⚠️ NOVO: Verificação adicional de confiança baixa
        confianca_baixa = (confianca < 0.60)
        if confianca_baixa and status == "NORMAL":
            logger.warning(f"⚠️ ALERTA: Confiança baixa ({confianca * 100:.1f}%) pode indicar contaminação!")
            status = "ANORMAL"  # Força status anormal se confiança < 60%

        logger.info(f"🏁 Resultado anomalia:")
        logger.info(f"   SVM detectou anomalia: {anomalia_svm}")
        logger.info(f"   MAD detectou anomalia: {anomalia_mad}")
        logger.info(f"   Confiança baixa (<60%): {confianca_baixa}")
        logger.info(f"   Status final: {status}")

        resultado = {
            'especie': especie_pred,
            'confianca': round(confianca * 100, 1),
            'status': status,
            'probabilidades': {
                classe: round(float(prob) * 100, 1)
                for classe, prob in zip(modelo_especies.classes_, prob_especies)
            },
            'indices': {
                col: round(float(val), 4)
                for col, val in zip(indices_cols, indices_array[0])
            },
            'detalhes_anomalia': {
                'svm_score': round(float(score_svm), 4),
                'svm_detectou': bool(anomalia_svm),
                'mad_violacoes': int(violacoes),
                'mad_detectou': bool(anomalia_mad),
                'confianca_baixa': bool(confianca_baixa),
                'logica_usada': 'AND + alerta confiança < 60%'
            },
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"✅ Predição: {especie_pred} ({confianca * 100:.1f}%) - {status}")

        return resultado

    except Exception as e:
        logger.error(f"❌ Erro na predição: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


# ==================== ENDPOINTS ESP32 ====================

@app.route('/esp32/poll', methods=['POST'])
def esp32_poll():
    """ESP32 verifica comandos pendentes"""
    try:
        data = request.json
        device_id = data.get('device_id', 'unknown')
        device_status = data.get('status', 'unknown')

        connected_devices[device_id] = {
            'id': device_id,
            'ip': request.remote_addr,
            'last_seen': datetime.now(),
            'status': device_status,
            'active': True
        }

        if device_id in pending_commands:
            command = pending_commands.pop(device_id)
            logger.info(f"📤 Enviando comando para {device_id}: {command['command']}")
            return jsonify(command)

        return jsonify({'command': 'status'})

    except Exception as e:
        logger.error(f"Erro em /esp32/poll: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/esp32/result', methods=['POST'])
def esp32_result():
    """Recebe espectro do ESP32 (18 bandas) e retorna classificação"""
    global last_analysis

    try:
        data = request.json
        device_id = data.get('device_id', 'unknown')
        spectrum = data.get('spectrum', [])

        logger.info(f"📊 Espectro recebido de {device_id}")
        logger.info(f"🔍 Valores-chave: r680={spectrum[10]:.6f}, r810={spectrum[14]:.6f}, r940={spectrum[17]:.6f}")

        # Realizar predição (função remove r485 internamente)
        resultado = prever_amostra(spectrum)
        resultado['device_id'] = device_id

        # Salvar no histórico
        with analysis_lock:
            last_analysis = resultado
            analysis_history.append(resultado)

        return jsonify(resultado)

    except Exception as e:
        logger.error(f"❌ Erro em /esp32/result: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'status': 'ERRO'}), 500


# ==================== INTERFACE WEB ====================

@app.route('/')
def home():
    """Página principal com botão de análise"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Classificador de Grãos</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1000px; margin: 0 auto; }

        .card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }

        h1 { color: #2d3748; margin-bottom: 10px; font-size: 2em; }

        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
            margin-left: 10px;
        }
        .status-online { background: #48bb78; color: white; }
        .status-offline { background: #f56565; color: white; }

        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 1.2em;
            border-radius: 30px;
            cursor: pointer;
            transition: transform 0.2s;
            font-weight: bold;
            display: inline-block;
        }
        .btn:hover { transform: scale(1.05); }
        .btn:disabled {
            background: #cbd5e0;
            cursor: not-allowed;
            transform: none;
        }

        .devices {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .device-card {
            background: #f7fafc;
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }
        .device-card.active { border-left-color: #48bb78; }

        .result-container {
            margin-top: 30px;
            padding: 25px;
            background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
            border-radius: 15px;
            border: 2px solid #e2e8f0;
        }

        .result-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #cbd5e0;
        }

        .especie-tag {
            display: inline-block;
            padding: 10px 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 25px;
            font-size: 1.5em;
            font-weight: bold;
        }

        .confianca-badge {
            font-size: 1.8em;
            font-weight: bold;
            color: #2d3748;
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
        }
        .status-normal { background: #c6f6d5; color: #22543d; }
        .status-anormal { background: #fed7d7; color: #742a2a; }

        .probs-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .prob-item {
            background: white;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .prob-label { 
            font-size: 0.9em; 
            color: #718096; 
            margin-bottom: 5px;
        }
        .prob-value { 
            font-size: 1.5em; 
            font-weight: bold; 
            color: #2d3748;
        }

        .indices-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-top: 15px;
        }
        .indice-item {
            background: white;
            padding: 12px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .anomaly-details {
            background: #fff5f5;
            border: 2px solid #fc8181;
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
        }

        .anomaly-details h4 {
            color: #c53030;
            margin-bottom: 10px;
        }

        .anomaly-details p {
            margin: 5px 0;
            font-size: 0.95em;
        }

        .loading {
            display: none;
            text-align: center;
            color: #667eea;
            font-weight: bold;
            margin-top: 15px;
        }
        .loading.active { display: block; }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .loading.active::after {
            content: '...';
            animation: pulse 1.5s infinite;
        }

        .timestamp {
            text-align: center;
            color: #718096;
            font-size: 0.85em;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #e2e8f0;
        }

        .info-badge {
            display: inline-block;
            background: #bee3f8;
            color: #2c5282;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: bold;
            margin: 5px;
        }

        .warning-badge {
            display: inline-block;
            background: #feebc8;
            color: #7c2d12;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: bold;
            margin: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>
                🌾 Classificador de Grãos
                <span id="status-badge" class="status-badge status-offline">Offline</span>
            </h1>
            <p style="color: #718096; margin-top: 10px;">
                Sistema de classificação espectral com Machine Learning
            </p>
            <div style="margin-top: 15px;">
                <span class="info-badge">✨ Modelo Otimizado (sem r485)</span>
                <span class="info-badge">🔬 Lógica AND + Alerta Confiança</span>
                <span class="info-badge">📡 17 bandas espectrais</span>
                <span class="warning-badge">⚠️ Limiar MAD: 2 violações</span>
                <span class="warning-badge">🎯 Alerta: confiança < 60%</span>
            </div>
        </div>

        <div class="card">
            <h2 style="margin-bottom: 20px;">📱 Dispositivos Conectados</h2>
            <div id="devices" class="devices">
                <p style="color: #718096;">Aguardando dispositivos...</p>
            </div>
        </div>

        <div class="card">
            <h2 style="margin-bottom: 20px;">🔬 Análise de Amostra</h2>
            <button id="analyze-btn" class="btn" onclick="analisarAmostra()">
                ⚡ Analisar Amostra
            </button>
            <div id="loading" class="loading">
                Aguardando resposta do ESP32
            </div>
        </div>

        <div id="result-card" class="card" style="display: none;">
            <h2 style="margin-bottom: 20px;">📊 Resultado da Análise</h2>
            <div id="result-content"></div>
        </div>
    </div>

    <script>
        let updateInterval;
        let lastTimestamp = null;
        let isWaitingForResult = false;

        function updateStatus() {
            fetch('/status')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('status-badge');
                    if (data.modelo_carregado) {
                        badge.className = 'status-badge status-online';
                        badge.textContent = 'Online';
                        document.getElementById('analyze-btn').disabled = false;
                    } else {
                        badge.className = 'status-badge status-offline';
                        badge.textContent = 'Modelo não carregado';
                        document.getElementById('analyze-btn').disabled = true;
                    }
                });
        }

        function updateDevices() {
            fetch('/devices')
                .then(r => r.json())
                .then(devices => {
                    const container = document.getElementById('devices');
                    if (devices.length === 0) {
                        container.innerHTML = '<p style="color: #718096;">Nenhum dispositivo conectado</p>';
                        return;
                    }

                    container.innerHTML = devices.map(d => `
                        <div class="device-card ${d.active ? 'active' : ''}">
                            <div style="font-weight: bold; margin-bottom: 5px;">
                                ${d.active ? '🟢' : '🔴'} ${d.id.substring(0, 12)}
                            </div>
                            <div style="font-size: 0.85em; color: #718096;">
                                ${d.ip}<br>
                                ${d.status}
                            </div>
                        </div>
                    `).join('');
                });
        }

        function analisarAmostra() {
            document.getElementById('analyze-btn').disabled = true;
            document.getElementById('loading').classList.add('active');
            isWaitingForResult = true;

            fetch('/command/analyze', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({device_id: 'auto'})
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    alert('Erro: ' + data.error);
                    document.getElementById('analyze-btn').disabled = false;
                    document.getElementById('loading').classList.remove('active');
                    isWaitingForResult = false;
                } else {
                    setTimeout(checkResult, 3000);
                }
            });
        }

        function checkResult() {
            if (!isWaitingForResult) return;

            fetch('/last_analysis')
                .then(r => r.json())
                .then(data => {
                    if (data.timestamp && data.timestamp !== lastTimestamp) {
                        lastTimestamp = data.timestamp;
                        displayResult(data);
                        document.getElementById('analyze-btn').disabled = false;
                        document.getElementById('loading').classList.remove('active');
                        isWaitingForResult = false;
                    } else if (isWaitingForResult) {
                        setTimeout(checkResult, 2000);
                    }
                });
        }

        function displayResult(data) {
            const card = document.getElementById('result-card');
            const content = document.getElementById('result-content');

            const statusClass = data.status === 'NORMAL' ? 'status-normal' : 'status-anormal';
            const statusIcon = data.status === 'NORMAL' ? '✔' : '⚠';

            const probsHtml = Object.entries(data.probabilidades)
                .sort((a, b) => b[1] - a[1])
                .map(([esp, prob]) => `
                    <div class="prob-item">
                        <div class="prob-label">${esp}</div>
                        <div class="prob-value">${prob}%</div>
                    </div>
                `).join('');

            const indicesHtml = Object.entries(data.indices)
                .map(([idx, val]) => `
                    <div class="indice-item">
                        <span style="color: #718096;">${idx}</span>
                        <strong>${val}</strong>
                    </div>
                `).join('');

            let anomalyDetailsHtml = '';
            if (data.detalhes_anomalia) {
                const det = data.detalhes_anomalia;
                const confAlert = det.confianca_baixa ? '⚠️ SIM' : '✅ NÃO';
                anomalyDetailsHtml = `
                    <div class="anomaly-details">
                        <h4>🔍 Detalhes da Detecção de Anomalias</h4>
                        <p><strong>Lógica:</strong> ${det.logica_usada}</p>
                        <p><strong>SVM Score:</strong> ${det.svm_score} 
                           ${det.svm_detectou ? '❌ (Anomalia)' : '✅ (Normal)'}</p>
                        <p><strong>Violações MAD:</strong> ${det.mad_violacoes}/4 índices 
                           ${det.mad_detectou ? '❌ (≥2 violações)' : '✅ (<2 violações)'}</p>
                        <p><strong>Confiança Baixa (<60%):</strong> ${confAlert}</p>
                        <p style="margin-top: 10px; font-style: italic; color: #718096;">
                            Status marcado como ANORMAL quando: (SVM E MAD concordam) OU (Confiança < 60%)
                        </p>
                    </div>
                `;
            }

            content.innerHTML = `
                <div class="result-container">
                    <div class="result-header">
                        <span class="especie-tag">${data.especie}</span>
                        <span class="confianca-badge">${data.confianca}%</span>
                        <span class="status-indicator ${statusClass}">
                            ${statusIcon} ${data.status}
                        </span>
                    </div>

                    <h3 style="margin-top: 25px; margin-bottom: 15px; color: #2d3748;">
                        Probabilidades por Espécie
                    </h3>
                    <div class="probs-grid">${probsHtml}</div>

                    <h3 style="margin-top: 25px; margin-bottom: 15px; color: #2d3748;">
                        Índices Espectrais
                    </h3>
                    <div class="indices-grid">${indicesHtml}</div>

                    ${anomalyDetailsHtml}

                    <div class="timestamp">
                        📅 ${new Date(data.timestamp).toLocaleString('pt-BR')}
                    </div>
                </div>
            `;

            card.style.display = 'block';
            card.scrollIntoView({behavior: 'smooth'});
        }

        updateStatus();
        updateDevices();
        updateInterval = setInterval(() => {
            updateStatus();
            updateDevices();
        }, 2000);
    </script>
</body>
</html>
    """


@app.route('/command/analyze', methods=['POST'])
def send_analyze_command():
    """Envia comando de análise para ESP32"""
    try:
        data = request.json
        device_id = data.get('device_id', 'auto')

        logger.info("🎯 Comando de análise solicitado")

        if device_id == 'auto':
            if connected_devices:
                now = datetime.now()
                active_devices = [
                    d for d in connected_devices.values()
                    if (now - d['last_seen']).total_seconds() < DEVICE_TIMEOUT
                ]

                if active_devices:
                    recent_device = max(active_devices, key=lambda x: x['last_seen'])
                    device_id = recent_device['id']
                else:
                    return jsonify({'error': 'Nenhum dispositivo ativo'}), 404
            else:
                return jsonify({'error': 'Nenhum dispositivo conectado'}), 404

        pending_commands[device_id] = {
            'command': 'analyze',
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"✅ Comando criado para: {device_id}")

        return jsonify({
            'status': 'command_queued',
            'device_id': device_id
        })

    except Exception as e:
        logger.error(f"Erro ao criar comando: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/devices', methods=['GET'])
def get_devices():
    """Lista dispositivos conectados"""
    try:
        now = datetime.now()
        devices_list = []

        for device_id, device_info in connected_devices.items():
            time_diff = (now - device_info['last_seen']).total_seconds()
            device_info['active'] = time_diff < DEVICE_TIMEOUT

            device_data = device_info.copy()
            device_data['last_seen'] = device_info['last_seen'].isoformat()
            devices_list.append(device_data)

        devices_list.sort(key=lambda x: x['last_seen'], reverse=True)
        return jsonify(devices_list)

    except Exception as e:
        logger.error(f"Erro ao listar dispositivos: {e}")
        return jsonify([])


@app.route('/last_analysis', methods=['GET'])
def get_last_analysis():
    """Retorna última análise"""
    with analysis_lock:
        if last_analysis:
            return jsonify(last_analysis)
    return jsonify({})


@app.route('/history', methods=['GET'])
def get_history():
    """Retorna histórico de análises"""
    try:
        with analysis_lock:
            history_list = list(analysis_history)
        return jsonify(history_list[::-1])
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        return jsonify([])


@app.route('/status', methods=['GET'])
def system_status():
    """Status do sistema"""
    try:
        now = datetime.now()
        active_devices = sum(
            1 for d in connected_devices.values()
            if (now - d['last_seen']).total_seconds() < DEVICE_TIMEOUT
        )

        return jsonify({
            'status': 'online',
            'modelo_carregado': MODELOS is not None,
            'especies_disponiveis': list(modelo_especies.classes_) if MODELOS else [],
            'devices_connected': active_devices,
            'bandas_modelo': len(bandas_cols) if MODELOS else 0,
            'bandas_esp32': 18,
            'indices_usados': list(indices_cols) if MODELOS else [],
            'config_anomalia': {
                'logica': 'AND + alerta confiança',
                'violacoes_mad_minimas': 2,
                'limiar_confianca': 60,
                'descricao': 'Mais sensível - detecta contaminações'
            },
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/export', methods=['GET'])
def export_data():
    """Exporta histórico em formato CSV"""
    try:
        import csv
        from io import StringIO
        from flask import Response

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow([
            'Timestamp', 'Device ID', 'Espécie', 'Confiança %', 'Status',
            'I1_NDVI', 'I2_Water', 'I3_Lipid', 'I4_Slope_Alt',
            'SVM Score', 'SVM Anomalia', 'MAD Violações', 'MAD Anomalia', 'Confiança Baixa'
        ])

        with analysis_lock:
            for analysis in analysis_history:
                indices = analysis.get('indices', {})
                detalhes = analysis.get('detalhes_anomalia', {})

                writer.writerow([
                    analysis.get('timestamp', ''),
                    analysis.get('device_id', ''),
                    analysis.get('especie', ''),
                    analysis.get('confianca', ''),
                    analysis.get('status', ''),
                    indices.get('I1_NDVI', ''),
                    indices.get('I2_Water', ''),
                    indices.get('I3_Lipid', ''),
                    indices.get('I4_Slope_Alt', ''),
                    detalhes.get('svm_score', ''),
                    detalhes.get('svm_detectou', ''),
                    detalhes.get('mad_violacoes', ''),
                    detalhes.get('mad_detectou', ''),
                    detalhes.get('confianca_baixa', '')
                ])

        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=analise_graos_{timestamp}.csv'
            }
        )

    except Exception as e:
        logger.error(f"Erro ao exportar dados: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/config', methods=['GET'])
def get_config():
    """Retorna configuração atual do sistema"""
    try:
        return jsonify({
            'especies': list(modelo_especies.classes_) if MODELOS else [],
            'bandas_espectrais': bandas_cols if MODELOS else [],
            'indices_calculados': list(indices_cols) if MODELOS else [],
            'deteccao_anomalia': {
                'logica': 'AND + alerta confiança',
                'violacoes_mad_minimas': 2,
                'limiar_confianca': 60,
                'descricao_mad': 'Median Absolute Deviation com fator 2.5',
                'descricao_svm': 'One-Class SVM com kernel RBF e nu=0.05',
                'descricao_confianca': 'Confiança < 60% indica possível contaminação'
            },
            'pca': {
                'componentes': 6,
                'variancia_explicada': float(pca.explained_variance_ratio_.sum()) if MODELOS else 0
            },
            'observacoes': {
                'banda_removida': 'r485 (índice 3)',
                'esp32_envia': '18 bandas',
                'modelo_usa': '17 bandas',
                'indices_novos': 'I1_NDVI, I2_Water, I3_Lipid, I4_Slope_Alt',
                'versao': 'Corrigida - MAD=2, alerta confiança<60%'
            }
        })
    except Exception as e:
        logger.error(f"Erro ao obter configuração: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== LIMPEZA ====================

def cleanup_old_data():
    """Remove dispositivos inativos e comandos antigos"""
    while True:
        try:
            time.sleep(60)
            now = datetime.now()

            devices_to_remove = []
            for device_id, device_info in connected_devices.items():
                if (now - device_info['last_seen']).total_seconds() > 300:
                    devices_to_remove.append(device_id)

            for device_id in devices_to_remove:
                del connected_devices[device_id]
                logger.info(f"🗑️ Dispositivo removido (inativo): {device_id}")

            commands_to_remove = []
            for device_id, command in pending_commands.items():
                cmd_time = datetime.fromisoformat(command['timestamp'])
                if (now - cmd_time).total_seconds() > 60:
                    commands_to_remove.append(device_id)

            for device_id in commands_to_remove:
                del pending_commands[device_id]

        except Exception as e:
            logger.error(f"Erro na limpeza: {e}")


# ==================== MAIN ====================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🌾 CLASSIFICADOR DE GRÃOS - SERVIDOR FLASK")
    logger.info("   Versão Corrigida - Detecção Melhorada")
    logger.info("=" * 60)

    if not carregar_modelo():
        logger.error("⚠️ Servidor iniciará SEM modelo!")
        logger.error("   Coloque 'modelo_completo_graos.pkl' na pasta")
    else:
        logger.info("\n✨ CONFIGURAÇÃO DE ANOMALIA (VERSÃO CORRIGIDA):")
        logger.info("   Lógica: AND (ambos métodos devem concordar)")
        logger.info("   Violações MAD mínimas: 2 (ajustado de 3)")
        logger.info("   Alerta de confiança baixa: < 60%")
        logger.info("   Resultado: Balanceado - detecta contaminações sem excesso de falsos positivos")
        logger.info("\n✂️ PROCESSAMENTO DE BANDAS:")
        logger.info("   ESP32 envia: 18 bandas")
        logger.info("   Servidor remove: r485 (índice 3)")
        logger.info("   Modelo usa: 17 bandas")
        logger.info("\n📊 ÍNDICES ESPECTRAIS:")
        logger.info("   I1_NDVI, I2_Water, I3_Lipid, I4_Slope_Alt")

    cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
    cleanup_thread.start()

    logger.info("\n" + "=" * 60)
    logger.info("🌐 Servidor Flask iniciando...")
    logger.info("📱 Acesse de qualquer dispositivo:")
    logger.info("   Local:  http://localhost:5000")
    logger.info("   Rede:   http://seu_ip_local:5000")
    logger.info("\n📡 Endpoints disponíveis:")
    logger.info("   POST /esp32/poll        - ESP32 verifica comandos")
    logger.info("   POST /esp32/result      - ESP32 envia espectro (18 bandas)")
    logger.info("   POST /command/analyze   - Interface solicita análise")
    logger.info("   GET  /devices           - Lista dispositivos")
    logger.info("   GET  /last_analysis     - Última análise")
    logger.info("   GET  /history           - Histórico completo")
    logger.info("   GET  /status            - Status do sistema")
    logger.info("   GET  /config            - Configuração atual")
    logger.info("   GET  /export            - Exportar CSV")
    logger.info("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False)