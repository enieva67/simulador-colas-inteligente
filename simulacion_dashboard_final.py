import streamlit as st
import heapq
import random
from collections import deque
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# Configuración inicial
st.set_page_config(page_title="Simulador Bancario - Analytics", layout="wide")

# ==========================================
# 1. MOTOR DE SIMULACIÓN (Igual al anterior, optimizado)
# ==========================================

def curva_demanda_diaria(hora_actual, tasa_base):
    # Patrón de demanda: Valle -> Subida -> PICO -> Bajada
    if 0 <= hora_actual < 2:   factor = 0.4
    elif 2 <= hora_actual < 3: factor = 0.8
    elif 3 <= hora_actual < 5: factor = 1.8  # HORA PICO
    elif 5 <= hora_actual < 7: factor = 1.2
    elif 7 <= hora_actual <= 8: factor = 0.6
    else: factor = 0.0
    return tasa_base * factor

class Cliente:
    def __init__(self, id_cliente, hora_llegada):
        self.id = id_cliente
        self.hora_llegada = hora_llegada
        self.hora_inicio_atencion = None
        self.cola_al_llegar = 0

class Servidor:
    def __init__(self, id_servidor):
        self.id = id_servidor
        self.activo = False
        self.ocupado = False
        self.tiempo_acumulado_activo = 0.0
        self.tiempo_acumulado_trabajando = 0.0

class SimulacionMaster:
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
        for i in range(min_serv): self.servidores[i].activo = True
            
        self.eventos = []
        self.historial_clientes = []
        self.log_sistema = [] 
        
        self.contador_activaciones = 0
        self.contador_desactivaciones = 0

    def _actualizar_cronometros(self, delta_tiempo):
        for s in self.servidores:
            if s.activo:
                s.tiempo_acumulado_activo += delta_tiempo

    def _get_tasa_actual(self):
        return curva_demanda_diaria(self.reloj, self.tasa_base)

    def _calcular_ewt(self):
        activos = sum(1 for s in self.servidores if s.activo)
        if activos == 0: return 999.0
        return len(self.cola_clientes) / (activos * self.mu)

    def _registrar_snapshot(self):
        activos = sum(1 for s in self.servidores if s.activo)
        ocupados = sum(1 for s in self.servidores if s.ocupado)
        
        self.log_sistema.append({
            'Tiempo': self.reloj,
            'Cola': len(self.cola_clientes),
            'Servidores_Activos': activos,
            'Wait_Time_Estimado_Min': self._calcular_ewt() * 60
        })

    def _gestionar_auto_scaling(self, ewt_actual):
        activos = sum(1 for s in self.servidores if s.activo)
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            for s in self.servidores:
                if not s.activo:
                    s.activo = True
                    self.contador_activaciones += 1
                    return 
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    s.activo = False
                    self.contador_desactivaciones += 1
                    return

    def correr(self):
        self._programar_llegada()
        
        # UI: Barra de progreso vacía al inicio
        progress_bar = st.progress(0)
        
        while self.eventos:
            tiempo_evento, tipo, data = heapq.heappop(self.eventos)
            
            delta = tiempo_evento - self.reloj
            self._actualizar_cronometros(delta)
            self.reloj = tiempo_evento
            
            if tipo == "LLEGADA":
                if self.reloj > 8.0: continue # Cierre de puerta
                
                c = Cliente(len(self.historial_clientes) + len(self.cola_clientes), self.reloj)
                c.cola_al_llegar = len(self.cola_clientes)
                
                ewt = self._calcular_ewt()
                self._gestionar_auto_scaling(ewt)
                
                self.cola_clientes.append(c)
                self._intentar_asignar()
                self._programar_llegada()
                self._registrar_snapshot()
                
            elif tipo == "SALIDA":
                srv_id = data
                self.servidores[srv_id].ocupado = False
                self._intentar_asignar()
                if not self.cola_clientes: self._gestionar_auto_scaling(0.0)
                self._registrar_snapshot()
            
            if random.random() < 0.05:
                progress_bar.progress(min(self.reloj / 8.0, 1.0))
        
        progress_bar.empty()
        return self._generar_reportes()

    def _programar_llegada(self):
        tasa = self._get_tasa_actual()
        if tasa <= 0: return
        tiempo = random.expovariate(tasa)
        if self.reloj + tiempo <= 8.0:
            heapq.heappush(self.eventos, (self.reloj + tiempo, "LLEGADA", None))

    def _intentar_asignar(self):
        if not self.cola_clientes: return
        candidato = next((s for s in self.servidores if s.activo and not s.ocupado), None)
        if candidato:
            cliente = self.cola_clientes.popleft()
            candidato.ocupado = True
            cliente.hora_inicio_atencion = self.reloj
            duracion = random.expovariate(self.mu)
            
            candidato.tiempo_acumulado_trabajando += duracion
            
            self.historial_clientes.append(cliente)
            heapq.heappush(self.eventos, (self.reloj + duracion, "SALIDA", candidato.id))

    def _generar_reportes(self):
        # Clientes
        data_c = []
        for c in self.historial_clientes:
            wait = (c.hora_inicio_atencion - c.hora_llegada) * 60
            data_c.append({
                "Llegada": c.hora_llegada,
                "Espera_Real_Min": wait,
                "Cola_Al_Llegar": c.cola_al_llegar
            })
        df_clientes = pd.DataFrame(data_c)
        
        # Sistema
        df_sistema = pd.DataFrame(self.log_sistema)
        
        # Servidores
        data_s = []
        for s in self.servidores:
            if s.tiempo_acumulado_activo > 0.001:
                util = (s.tiempo_acumulado_trabajando / s.tiempo_acumulado_activo) * 100
            else:
                util = 0.0
            data_s.append({
                "ID": f"Cajero {s.id}",
                "Horas_Activo": s.tiempo_acumulado_activo,
                "Utilizacion_Pct": util
            })
        df_servidores = pd.DataFrame(data_s)
        
        return df_clientes, df_sistema, df_servidores

# ==========================================
# 2. ETL AVANZADO: ARREGLO DE SERIES TEMPORALES
# ==========================================

def procesar_series_tiempo(df_sistema, df_clientes):
    """
    Combina datos y ARREGLA HUECOS para gráficos continuos.
    """
    # Definir rango completo de 8 horas (minuto a minuto)
    base_time = pd.Timestamp("2024-01-01 08:00:00")
    full_range = pd.date_range(start=base_time, end=base_time + pd.Timedelta(hours=8), freq='1T')
    
    # 1. Procesar Sistema (Estado Continuo)
    df_sistema['datetime'] = base_time + pd.to_timedelta(df_sistema['Tiempo'], unit='h')
    df_sys = df_sistema.set_index('datetime')
    
    # Resample a 1T y usar 'ffill' (Forward Fill)
    # Si en el minuto 10:05 no pasó nada, el estado es igual al de 10:04.
    df_sys_clean = df_sys.resample('1T').agg({
        'Cola': 'last',
        'Servidores_Activos': 'last',
        'Wait_Time_Estimado_Min': 'last'
    }).reindex(full_range).ffill().fillna(0) # fillna(0) para el inicio si no hay datos
    
    # 2. Procesar Clientes (Eventos Discretos)
    df_clientes['datetime'] = base_time + pd.to_timedelta(df_clientes['Llegada'], unit='h')
    df_cl = df_clientes.set_index('datetime')
    
    # Resample a 1T
    df_cl_clean = df_cl.resample('1T').agg({
        'Espera_Real_Min': 'mean' # Promedio de quienes llegaron
    }).reindex(full_range)
    
    # TRUCO PARA GRÁFICO SUAVE: Interpolación
    # Si nadie llegó en un minuto, interpolamos entre el anterior y el siguiente
    # para que la línea roja no se corte visualmente.
    df_cl_clean['Espera_Real_Min'] = df_cl_clean['Espera_Real_Min'].interpolate(method='linear').fillna(0)
    
    # 3. Unir
    df_master = df_sys_clean.join(df_cl_clean)
    
    return df_master

# ==========================================
# 3. DASHBOARD CON PERSISTENCIA (SESSION STATE)
# ==========================================

st.title("🏦 Dashboard de Operaciones Bancarias")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuración")
    TASA_BASE = st.slider("Demanda Base (Clientes/h)", 50, 400, 150)
    MAX_SERVERS = st.slider("Cajeros Máximos", 5, 40, 15)
    TASA_SERVICIO = st.slider("Velocidad Cajero (pax/h)", 10, 60, 20)
    
    st.subheader("Auto-Scaling")
    c1, c2 = st.columns(2)
    UMBRAL_UP = c1.number_input("Activar (> min)", value=15)
    UMBRAL_DOWN = c2.number_input("Apagar (< min)", value=3)
    
    st.markdown("---")
    # Botón de ejecución
    run_clicked = st.button("🚀 CORRER NUEVA SIMULACIÓN", type="primary")

# --- GESTIÓN DE ESTADO (PERSISTENCIA) ---
if 'simulation_results' not in st.session_state:
    st.session_state['simulation_results'] = None

# Si se hace clic, corremos y GUARDAMOS en session_state
if run_clicked:
    sim = SimulacionMaster(TASA_BASE, TASA_SERVICIO, 1, MAX_SERVERS, UMBRAL_UP, UMBRAL_DOWN)
    with st.spinner("Simulando y procesando series temporales..."):
        df_c, df_s, df_srv = sim.correr()
        df_m = procesar_series_tiempo(df_s, df_c)
        
        # Guardar en memoria del navegador
        st.session_state['simulation_results'] = {
            'clientes': df_c,
            'servidores': df_srv,
            'master': df_m,
            'recambios': sim.contador_activaciones + sim.contador_desactivaciones
        }

# --- RENDERIZADO DEL DASHBOARD ---
# Solo mostramos si hay datos en memoria
results = st.session_state['simulation_results']

if results:
    df_master = results['master']
    df_clientes = results['clientes']
    df_servidores = results['servidores']
    
    # KPI BANNER
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tiempo Espera Real (Promedio)", f"{df_clientes['Espera_Real_Min'].mean():.2f} min")
    c2.metric("Pico de Cola", f"{df_master['Cola'].max():.0f} personas")
    c3.metric("Cajeros Promedio", f"{df_master['Servidores_Activos'].mean():.1f}")
    c4.metric("Total Recambios", f"{results['recambios']}")

    tab1, tab2, tab3 = st.tabs(["📈 Análisis Temporal", "⚙️ Eficiencia", "💾 Datos"])
    
    with tab1:
        st.subheader("Comparativa: Lo que se promete vs. Lo que pasa")
        st.caption("Gracias a la interpolación y el rellenado de datos, estas líneas ya no se cortan incluso con baja demanda.")
        
        fig = go.Figure()
        
        # Estimado (Relleno)
        fig.add_trace(go.Scatter(
            x=df_master.index, y=df_master['Wait_Time_Estimado_Min'],
            name="Estimado (Sistema)", fill='tozeroy',
            line=dict(color='rgba(0,100,255,0.3)')
        ))
        
        # Real (Línea Sólida)
        fig.add_trace(go.Scatter(
            x=df_master.index, y=df_master['Espera_Real_Min'],
            name="Real (Cliente)",
            line=dict(color='red', width=2)
        ))
        
        fig.update_layout(title="Serie de Tiempo Continua", yaxis_title="Minutos de Espera", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.subheader("Utilización Real")
        df_active = df_servidores[df_servidores['Horas_Activo'] > 0.01]
        fig_bar = px.bar(df_active, x="ID", y="Utilizacion_Pct", 
                         color="Utilizacion_Pct", color_continuous_scale="RdYlGn_r",
                         range_y=[0, 105], title="Ocupación por Cajero")
        st.plotly_chart(fig_bar, use_container_width=True)

    with tab3:
        st.subheader("Descarga de Datos")
        st.info("Ahora puedes descargar sin que desaparezca el dashboard.")
        
        col1, col2 = st.columns(2)
        
        csv_master = df_master.to_csv().encode('utf-8')
        col1.download_button(
            "📥 Descargar Serie Temporal (CSV)", 
            csv_master, 
            "serie_tiempo_completa.csv", 
            "text/csv"
        )
        
        csv_clientes = df_clientes.to_csv().encode('utf-8')
        col2.download_button(
            "📥 Descargar Clientes Raw (CSV)", 
            csv_clientes, 
            "clientes_raw.csv", 
            "text/csv"
        )
        
        st.dataframe(df_master.head(10))

else:
    st.info("👈 Configura los parámetros y presiona 'CORRER NUEVA SIMULACIÓN'.")