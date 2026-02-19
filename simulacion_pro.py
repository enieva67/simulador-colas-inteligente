import streamlit as st
import heapq
import random
from collections import deque
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ==========================================
# 1. LÓGICA DE NEGOCIO (BACKEND)
# ==========================================

def curva_demanda_diaria(hora_actual, tasa_base):
    # Patrón de demanda: Mañana baja, pico mediodía, tarde media
    if 0 <= hora_actual < 2: factor = 0.4
    elif 2 <= hora_actual < 4: factor = 1.0
    elif 4 <= hora_actual < 6: factor = 1.8 # HORA PICO
    elif 6 <= hora_actual <= 8: factor = 0.6
    else: factor = 0.1
    return tasa_base * factor

class Cliente:
    def __init__(self, id, hora_llegada):
        self.id = id
        self.hora_llegada = hora_llegada
        self.hora_inicio_atencion = None
        self.hora_salida = None
        self.largo_cola_al_llegar = 0

class Servidor:
    def __init__(self, id):
        self.id = id
        self.activo = False
        self.ocupado = False
        # Métricas de eficiencia
        self.tiempo_total_activo = 0.0
        self.tiempo_total_ocupado = 0.0
        self.ultimo_cambio_estado = 0.0 # Para calcular delta tiempo activo

class SimulacionAvanzada:
    def __init__(self, tasa_base, tasa_servicio, min_serv, max_serv, umbral_up, umbral_down):
        self.tasa_base = tasa_base
        self.mu = tasa_servicio
        self.min_servers = min_serv
        self.max_servers = max_serv
        self.umbral_up = umbral_up / 60.0
        self.umbral_down = umbral_down / 60.0
        
        self.reloj = 0.0
        self.cola_clientes = deque()
        self.servidores = [Servidor(i) for i in range(max_serv)]
        
        # Inicializar mínimos
        for i in range(min_serv): 
            self.servidores[i].activo = True
            self.servidores[i].ultimo_cambio_estado = 0.0
            
        self.eventos = []
        self.historial_clientes = []
        self.log_serie_tiempo = [] # Log granular para CSV
        
        # KPIs Gerenciales
        self.contador_activaciones = 0
        self.contador_desactivaciones = 0

    def _actualizar_tiempos_servidores(self):
        """Suma el tiempo transcurrido a los contadores de los servidores activos"""
        # Esta función debe llamarse ANTES de actualizar self.reloj
        delta = 0.0
        # Simplemente necesitamos actualizar los acumuladores al final, 
        # pero para precisión, lo haremos evento tras evento si es necesario.
        # Por simplicidad en este modelo DES, calcularemos al final el tiempo activo total.
        pass

    def _get_tasa_actual(self):
        return curva_demanda_diaria(self.reloj, self.tasa_base)

    def _registrar_estado(self):
        activos = sum(1 for s in self.servidores if s.activo)
        ocupados = sum(1 for s in self.servidores if s.ocupado)
        tasa = self._get_tasa_actual()
        
        self.log_serie_tiempo.append({
            'Tiempo_Exacto': self.reloj,
            'Hora_Dia': self.reloj, # Mantener formato float para gráficos
            'Cola': len(self.cola_clientes),
            'Servidores_Activos': activos,
            'Servidores_Ocupados': ocupados,
            'Tasa_Llegada_Teorica': tasa,
            'Wait_Time_Estimado': self._calcular_ewt() * 60
        })

    def _calcular_ewt(self):
        activos = sum(1 for s in self.servidores if s.activo)
        if activos == 0: return 999.0
        return len(self.cola_clientes) / (activos * self.mu)

    def _cambiar_estado_servidor(self, servidor, nuevo_estado):
        # Antes de cambiar, calculamos cuánto tiempo estuvo en el estado anterior
        tiempo_en_estado = self.reloj - servidor.ultimo_cambio_estado
        
        if servidor.activo:
            servidor.tiempo_total_activo += tiempo_en_estado
            
        servidor.activo = nuevo_estado
        servidor.ultimo_cambio_estado = self.reloj
        
        if nuevo_estado: self.contador_activaciones += 1
        else: self.contador_desactivaciones += 1

    def _gestionar_escalado(self, ewt_actual):
        activos = sum(1 for s in self.servidores if s.activo)
        
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            for s in self.servidores:
                if not s.activo:
                    self._cambiar_estado_servidor(s, True)
                    return 
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    self._cambiar_estado_servidor(s, False)
                    return

    def correr_simulacion(self):
        # Primer evento
        self._programar_llegada()
        
        # UI
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        while self.eventos:
            tiempo, tipo, data = heapq.heappop(self.eventos)
            
            # Cierre del banco a las 8 horas (pero siguen atendiendo cola)
            if tipo == "LLEGADA" and tiempo > 8.0: continue
            
            # Actualizar tiempos de servidores antes de mover el reloj (opcional si usamos delta final)
            # Para simplificar, sumamos tiempos al final o en cambios de estado.
            # Haremos un barrido final.
            
            self.reloj = tiempo
            
            if tipo == "LLEGADA":
                c = Cliente(len(self.historial_clientes) + len(self.cola_clientes), self.reloj)
                c.largo_cola_al_llegar = len(self.cola_clientes)
                
                ewt = self._calcular_ewt()
                self._gestionar_escalado(ewt)
                
                self.cola_clientes.append(c)
                self._intentar_asignar()
                self._programar_llegada()
                self._registrar_estado()
                
            elif tipo == "SALIDA":
                srv_id = data
                srv = self.servidores[srv_id]
                srv.ocupado = False
                
                self._intentar_asignar()
                if not self.cola_clientes: self._gestionar_escalado(0.0)
                self._registrar_estado()
            
            # UI Updates
            if random.random() < 0.05: # No actualizar siempre para rendimiento
                p = min(self.reloj / 8.0, 1.0)
                progress_bar.progress(p)
                status_text.text(f"Simulando Hora: {self.reloj:.2f}...")

        progress_bar.empty()
        status_text.empty()
        
        # Cierre: Actualizar tiempos finales de servidores activos
        for s in self.servidores:
            if s.activo:
                s.tiempo_total_activo += (self.reloj - s.ultimo_cambio_estado)
                
        return self._generar_dataframes()

    def _programar_llegada(self):
        tasa = self._get_tasa_actual()
        tiempo = random.expovariate(tasa)
        heapq.heappush(self.eventos, (self.reloj + tiempo, "LLEGADA", None))

    def _intentar_asignar(self):
        if not self.cola_clientes: return
        
        candidato = next((s for s in self.servidores if s.activo and not s.ocupado), None)
        if candidato:
            cliente = self.cola_clientes.popleft()
            candidato.ocupado = True
            
            cliente.hora_inicio_atencion = self.reloj
            duracion = random.expovariate(self.mu)
            cliente.hora_salida = self.reloj + duracion
            
            # Métricas Servidor
            candidato.tiempo_total_ocupado += duracion
            
            self.historial_clientes.append(cliente)
            heapq.heappush(self.eventos, (cliente.hora_salida, "SALIDA", candidato.id))

    def _generar_dataframes(self):
        # 1. Clientes
        data_c = []
        for c in self.historial_clientes:
            data_c.append({
                "ID": c.id,
                "Llegada": c.hora_llegada,
                "Espera_Min": (c.hora_inicio_atencion - c.hora_llegada) * 60,
                "Cola_Llegar": c.largo_cola_al_llegar
            })
        df_clientes = pd.DataFrame(data_c)
        
        # 2. Log de Eventos (Raw)
        df_log = pd.DataFrame(self.log_serie_tiempo)
        
        # 3. Datos de Servidores (Utilización)
        data_s = []
        for s in self.servidores:
            # Evitar división por cero
            util = (s.tiempo_total_ocupado / s.tiempo_total_activo * 100) if s.tiempo_total_activo > 0 else 0
            data_s.append({
                "ID_Cajero": f"Cajero {s.id}",
                "Horas_Activo": s.tiempo_total_activo,
                "Horas_Trabajadas": s.tiempo_total_ocupado,
                "Utilizacion_Pct": util
            })
        df_servidores = pd.DataFrame(data_s)
        
        return df_clientes, df_log, df_servidores

# ==========================================
# 2. PROCESAMIENTO DE SERIES DE TIEMPO (ETL)
# ==========================================

def generar_dataset_timeseries(df_log):
    """
    Convierte el log de eventos irregulares en una serie de tiempo regular 
    (ej: cada 1 minuto) ideal para análisis de datos / Kaggle.
    """
    # Convertir float horas a timedelta para usar resampling de pandas
    # Asumimos que la simulación empieza hoy a las 8:00 AM
    start_time = pd.Timestamp("2023-01-01 08:00:00")
    
    # Crear columna datetime real
    df_log['datetime'] = start_time + pd.to_timedelta(df_log['Tiempo_Exacto'], unit='h')
    
    # Set index
    df_log = df_log.set_index('datetime')
    
    # Resamplear a 1 minuto (tomando el último valor conocido o promedio)
    # 'last' es mejor para estado (cola, servidores activos)
    # 'mean' para tasas
    df_resampled = df_log.resample('1T').agg({
        'Cola': 'last',
        'Servidores_Activos': 'last',
        'Servidores_Ocupados': 'last',
        'Tasa_Llegada_Teorica': 'mean',
        'Wait_Time_Estimado': 'mean',
        'Hora_Dia': 'last'
    }).fillna(method='ffill') # Rellenar huecos con el valor anterior
    
    return df_resampled

# ==========================================
# 3. FRONTEND (STREAMLIT)
# ==========================================

st.set_page_config(page_title="Simulador Bancario Pro", layout="wide")
st.title("🏦 Dashboard de Operaciones: Optimización de Colas")

# --- SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Centro de Control")
    TASA_BASE = st.slider("Demanda Base (Clientes/Hora)", 50, 300, 120)
    MAX_SERVERS = st.slider("Flota Máxima de Cajeros", 5, 30, 15)
    UMBRAL_UP = st.number_input("Activar si espera > (min)", 5, 30, 15)
    
    st.markdown("---")
    btn_run = st.button("🚀 Ejecutar Nueva Simulación", type="primary")

# --- LÓGICA PRINCIPAL ---
if btn_run:
    sim = SimulacionAvanzada(TASA_BASE, 20, 1, MAX_SERVERS, UMBRAL_UP, 5.0)
    
    with st.spinner("Procesando eventos discretos..."):
        df_clientes, df_log, df_servidores = sim.correr_simulacion()
        df_timeseries = generar_dataset_timeseries(df_log)

    # --- PESTAÑAS ---
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard Gerencial", "📈 Análisis de Demanda", "💾 Data Export"])

    # === TAB 1: GERENCIAL ===
    with tab1:
        st.subheader("KPIs de Rendimiento")
        
        # Cálculos SLA
        total_clientes = len(df_clientes)
        atendidos_rapido = len(df_clientes[df_clientes["Espera_Min"] < 10])
        sla_pct = (atendidos_rapido / total_clientes) * 100
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Nivel de Servicio (<10min)", f"{sla_pct:.1f}%", delta_color="normal")
        col2.metric("Espera Promedio", f"{df_clientes['Espera_Min'].mean():.1f} min")
        col3.metric("Recambios de Personal", f"{sim.contador_activaciones + sim.contador_desactivaciones}")
        col4.metric("Costo Promedio (Cajeros Activos)", f"{df_timeseries['Servidores_Activos'].mean():.1f}")

        st.divider()

        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("Eficiencia de la Fuerza Laboral")
            # Gráfico de Barras de Utilización
            fig_util = px.bar(df_servidores, x="ID_Cajero", y="Utilizacion_Pct",
                              title="¿Qué tan ocupados estuvieron los cajeros mientras estaban activos?",
                              color="Utilizacion_Pct", color_continuous_scale="RdYlGn", range_y=[0, 100],
                              labels={"Utilizacion_Pct": "% Ocupación"})
            fig_util.add_hline(y=85, line_dash="dot", annotation_text="Objetivo (85%)", line_color="green")
            st.plotly_chart(fig_util, use_container_width=True)
            
        with c2:
            st.subheader("Distribución de Espera")
            fig_hist = px.histogram(df_clientes, x="Espera_Min", nbins=30,
                                    title="Histograma de Tiempos", color_discrete_sequence=['#636EFA'])
            fig_hist.add_vline(x=UMBRAL_UP, line_color="red", annotation_text="Límite")
            st.plotly_chart(fig_hist, use_container_width=True)

    # === TAB 2: ANÁLISIS DEMANDA ===
    with tab2:
        st.subheader("Comportamiento durante la Hora Pico")
        
        fig_ts = go.Figure()
        
        # Área de Cola
        fig_ts.add_trace(go.Scatter(
            x=df_timeseries.index, y=df_timeseries['Cola'],
            name="Cola (Personas)", fill='tozeroy', line=dict(color='blue', width=1)
        ))
        
        # Línea de Cajeros
        fig_ts.add_trace(go.Scatter(
            x=df_timeseries.index, y=df_timeseries['Servidores_Activos'],
            name="Cajeros Activos", line=dict(color='red', width=3), yaxis="y2"
        ))
        
        fig_ts.update_layout(
            title="Respuesta del Auto-Scaling ante la Demanda",
            yaxis=dict(title="Personas en Espera"),
            yaxis2=dict(title="Cajeros", overlaying="y", side="right"),
            hovermode="x unified"
        )
        st.plotly_chart(fig_ts, use_container_width=True)
        
        st.markdown("### Mapa de Calor: Espera vs Hora")
        fig_scat = px.scatter(df_clientes, x="Llegada", y="Espera_Min", 
                              color="Cola_Llegar", title="¿A qué hora se sufre más?",
                              labels={"Llegada": "Hora del Día (0-8)", "Espera_Min": "Minutos Esperando"})
        st.plotly_chart(fig_scat, use_container_width=True)

    # === TAB 3: DATA EXPORT ===
    with tab3:
        st.subheader("📂 Generador de Datasets (Formato Kaggle)")
        st.markdown("""
        Esta tabla es el resultado de **resamplear los eventos discretos** a una serie de tiempo uniforme (minuto a minuto).
        Perfecto para entrenar modelos de Machine Learning (LSTM, Prophet) para predecir demanda futura.
        """)
        
        st.dataframe(df_timeseries.head(10))
        
        # Botón de Descarga
        csv = df_timeseries.to_csv().encode('utf-8')
        st.download_button(
            label="📥 Descargar Dataset (serie_tiempo_banco.csv)",
            data=csv,
            file_name='serie_tiempo_banco.csv',
            mime='text/csv',
        )
        
        st.markdown("### Resumen Estadístico del Dataset")
        st.write(df_timeseries.describe())

else:
    st.info("👈 Configura los parámetros y presiona 'Ejecutar' para iniciar el análisis.")