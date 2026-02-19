import streamlit as st
import heapq
import random
from collections import deque
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# Configuración de página al inicio (Requerido por Streamlit)
st.set_page_config(
    page_title="Simulador Bancario Master AI",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 1. LÓGICA DEL MOTOR DE SIMULACIÓN (DES)
# ==========================================

def curva_demanda_diaria(hora_actual, tasa_base):
    """
    Define la 'personalidad' del día.
    Devuelve la tasa de llegada (lambda) para un instante específico.
    """
    # Patrón: Mañana tranquila -> Subida -> HORA PICO (Almuerzo) -> Bajada -> Cierre
    if 0 <= hora_actual < 2:   factor = 0.4
    elif 2 <= hora_actual < 3: factor = 0.8
    elif 3 <= hora_actual < 5: factor = 1.8  # 🔥 HORA PICO (x1.8 demanda normal)
    elif 5 <= hora_actual < 7: factor = 1.2
    elif 7 <= hora_actual <= 8: factor = 0.6
    else: factor = 0.0
    return tasa_base * factor

class Cliente:
    def __init__(self, id_cliente, hora_llegada):
        self.id = id_cliente
        self.hora_llegada = hora_llegada # Float exacto
        self.hora_inicio_atencion = None
        self.hora_salida = None
        self.cola_al_llegar = 0

class Servidor:
    def __init__(self, id_servidor):
        self.id = id_servidor
        self.activo = False        # ¿Está en turno?
        self.ocupado = False       # ¿Está atendiendo?
        # Métricas precisas para utilización
        self.tiempo_acumulado_activo = 0.0
        self.tiempo_acumulado_trabajando = 0.0

class SimulacionMaster:
    def __init__(self, tasa_base, tasa_servicio, min_serv, max_serv, umbral_up, umbral_down):
        self.tasa_base = tasa_base
        self.mu = tasa_servicio
        self.min_servers = min_serv
        self.max_servers = max_serv
        # Convertimos minutos a horas (float)
        self.umbral_up = umbral_up / 60.0
        self.umbral_down = umbral_down / 60.0
        
        self.reloj = 0.0
        self.cola_clientes = deque()
        # Creamos la flota de servidores
        self.servidores = [Servidor(i) for i in range(max_serv)]
        
        # Encendemos los servidores mínimos
        for i in range(min_serv): 
            self.servidores[i].activo = True
            
        self.eventos = [] # Priority Queue
        self.historial_clientes = []
        self.log_sistema = [] # Foto del sistema en cada evento
        
        # Contadores Gerenciales
        self.contador_activaciones = 0
        self.contador_desactivaciones = 0

    def _actualizar_cronometros(self, delta_tiempo):
        """Suma tiempo a los contadores de los servidores activos"""
        for s in self.servidores:
            if s.activo:
                s.tiempo_acumulado_activo += delta_tiempo

    def _get_tasa_actual(self):
        return curva_demanda_diaria(self.reloj, self.tasa_base)

    def _calcular_ewt(self):
        """Estimated Wait Time (Tiempo Estimado por el Sistema)"""
        activos = sum(1 for s in self.servidores if s.activo)
        if activos == 0: return 999.0 # Infinito
        # EWT = Lq / (n * mu)
        return len(self.cola_clientes) / (activos * self.mu)

    def _registrar_snapshot(self):
        """Toma una foto del estado actual para el análisis posterior"""
        activos = sum(1 for s in self.servidores if s.activo)
        ocupados = sum(1 for s in self.servidores if s.ocupado)
        
        self.log_sistema.append({
            'Tiempo': self.reloj,
            'Cola': len(self.cola_clientes),
            'Servidores_Activos': activos,
            'Servidores_Ocupados': ocupados,
            'Tasa_Llegada_Instantanea': self._get_tasa_actual(),
            'Wait_Time_Estimado_Min': self._calcular_ewt() * 60
        })

    def _gestionar_auto_scaling(self, ewt_actual):
        """CEREBRO: Decide si prende o apaga servidores según EWT"""
        activos = sum(1 for s in self.servidores if s.activo)
        
        # REGLA 1: Escalar Hacia Arriba (Emergencia)
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            # Buscar el primer inactivo
            for s in self.servidores:
                if not s.activo:
                    s.activo = True
                    self.contador_activaciones += 1
                    return 
        
        # REGLA 2: Escalar Hacia Abajo (Ahorro)
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            # Buscar el último activo que esté libre
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    s.activo = False
                    self.contador_desactivaciones += 1
                    return

    def programar_llegada(self):
        tasa = self._get_tasa_actual()
        if tasa <= 0: return # Banco cerrado o error
        
        # Generar intervalo
        tiempo = random.expovariate(tasa)
        hora_evento = self.reloj + tiempo
        
        # Solo agendar si es antes del cierre (8 horas)
        if hora_evento <= 8.0:
            heapq.heappush(self.eventos, (hora_evento, "LLEGADA", None))

    def intentar_asignar(self):
        """Busca match entre servidor libre y cliente en cola"""
        if not self.cola_clientes: return
        
        # Buscar candidato (activo y no ocupado)
        candidato = next((s for s in self.servidores if s.activo and not s.ocupado), None)
        
        if candidato:
            cliente = self.cola_clientes.popleft()
            candidato.ocupado = True
            
            cliente.hora_inicio_atencion = self.reloj
            duracion = random.expovariate(self.mu)
            cliente.hora_salida = self.reloj + duracion
            
            # Registrar uso
            candidato.tiempo_acumulado_trabajando += duracion
            
            self.historial_clientes.append(cliente)
            heapq.heappush(self.eventos, (cliente.hora_salida, "SALIDA", candidato.id))

    def correr(self):
        # Primer evento
        self.programar_llegada()
        
        # UI Progress
        progress_bar = st.progress(0)
        
        while self.eventos:
            tiempo_evento, tipo, data = heapq.heappop(self.eventos)
            
            # 1. Actualizar cronómetros ANTES de saltar el tiempo
            delta = tiempo_evento - self.reloj
            self._actualizar_cronometros(delta)
            
            # 2. Actualizar Reloj
            self.reloj = tiempo_evento
            
            # 3. Manejar Evento
            if tipo == "LLEGADA":
                # Nace Cliente
                c = Cliente(len(self.historial_clientes) + len(self.cola_clientes), self.reloj)
                c.cola_al_llegar = len(self.cola_clientes)
                
                # Calcular métricas para decisión
                ewt = self._calcular_ewt()
                self._gestionar_auto_scaling(ewt)
                
                self.cola_clientes.append(c)
                self.intentar_asignar()
                self.programar_llegada()
                self._registrar_snapshot() # FOTO
                
            elif tipo == "SALIDA":
                srv_id = data
                self.servidores[srv_id].ocupado = False
                
                self.intentar_asignar()
                if not self.cola_clientes: self._gestionar_auto_scaling(0.0)
                self._registrar_snapshot() # FOTO
            
            # Actualizar UI cada tanto (no siempre para no frenar)
            if random.random() < 0.05:
                progress_bar.progress(min(self.reloj / 8.0, 1.0))
        
        progress_bar.empty()
        
        # --- PROCESAMIENTO DE DATOS AL FINALIZAR ---
        return self._generar_reportes()

    def _generar_reportes(self):
        # 1. DF Clientes (Realidad)
        data_c = []
        for c in self.historial_clientes:
            wait = (c.hora_inicio_atencion - c.hora_llegada) * 60
            data_c.append({
                "ID": c.id,
                "Llegada": c.hora_llegada,
                "Espera_Real_Min": wait,
                "Cola_Al_Llegar": c.cola_al_llegar
            })
        df_clientes = pd.DataFrame(data_c)
        
        # 2. DF Sistema (Estimaciones y Estado)
        df_sistema = pd.DataFrame(self.log_sistema)
        
        # 3. DF Servidores (Eficiencia)
        data_s = []
        for s in self.servidores:
            if s.tiempo_acumulado_activo > 0.001:
                util = (s.tiempo_acumulado_trabajando / s.tiempo_acumulado_activo) * 100
            else:
                util = 0.0
            
            data_s.append({
                "ID": f"Cajero {s.id}",
                "Horas_Activo": s.tiempo_acumulado_activo,
                "Horas_Trabajadas": s.tiempo_acumulado_trabajando,
                "Utilizacion_Pct": util
            })
        df_servidores = pd.DataFrame(data_s)
        
        return df_clientes, df_sistema, df_servidores

# ==========================================
# 2. FUNCIONES DE ANÁLISIS DE DATOS (ETL)
# ==========================================

def fusionar_realidad_vs_estimado(df_sistema, df_clientes):
    """
    Crea el Dataset Maestro cruzando lo que el sistema 'veía' vs lo que 'pasó'.
    Usa resampling de 1 minuto para suavizar ruido visual.
    """
    # Crear índice temporal ficticio (asumiendo apertura 8:00 AM)
    base_time = pd.Timestamp("2024-01-01 08:00:00")
    
    # 1. Procesar Sistema
    df_sistema['datetime'] = base_time + pd.to_timedelta(df_sistema['Tiempo'], unit='h')
    df_sys_resampled = df_sistema.set_index('datetime').resample('1T').agg({
        'Cola': 'max', # Peor caso del minuto
        'Servidores_Activos': 'last', # Estado final del minuto
        'Wait_Time_Estimado_Min': 'mean', # Promedio de estimación
        'Tasa_Llegada_Instantanea': 'mean'
    })
    
    # 2. Procesar Clientes (Realidad)
    df_clientes['datetime'] = base_time + pd.to_timedelta(df_clientes['Llegada'], unit='h')
    df_cl_resampled = df_clientes.set_index('datetime').resample('1T').agg({
        'Espera_Real_Min': 'mean', # Promedio real de los que llegaron en ese minuto
        'ID': 'count' # Cantidad de llegadas (Volumen)
    })
    
    # 3. Join
    df_master = df_sys_resampled.join(df_cl_resampled)
    
    # Limpieza: Si nadie llegó, interpolamos la espera real para que el gráfico no se corte
    df_master['Espera_Real_Min'] = df_master['Espera_Real_Min'].interpolate(method='linear')
    df_master['Volumen_Clientes'] = df_master['ID'].fillna(0)
    
    # Calcular el Sesgo (Bias)
    df_master['Sesgo_Algoritmo'] = df_master['Espera_Real_Min'] - df_master['Wait_Time_Estimado_Min']
    
    return df_master

# ==========================================
# 3. INTERFAZ GRÁFICA (DASHBOARD)
# ==========================================

st.title("🏦 Simulador Bancario: Optimización Operativa & Analytics")
st.markdown("### Plataforma de Simulación de Colas M/M/c con Auto-Scaling")

# --- SIDEBAR DE CONTROL ---
with st.sidebar:
    st.header("🎛️ Centro de Control")
    
    st.subheader("1. Perfil de Demanda")
    TASA_BASE = st.slider("Clientes Base / Hora", 50, 400, 150, help="Volumen en horas normales. La hora pico multiplicará esto por 1.8x")
    
    st.subheader("2. Capacidad Operativa")
    MAX_SERVERS = st.slider("Flota Máxima de Cajeros", 5, 40, 15)
    TASA_SERVICIO = st.slider("Velocidad Cajero (Pax/Hora)", 10, 60, 20)
    
    st.subheader("3. Política de Auto-Scaling")
    st.info("Reglas para prender/apagar cajeros automáticamente.")
    col1, col2 = st.columns(2)
    UMBRAL_UP = col1.number_input("Activar (> min)", 5, 60, 15)
    UMBRAL_DOWN = col2.number_input("Apagar (< min)", 1, 30, 3)
    
    st.markdown("---")
    btn_run = st.button("🚀 INICIAR SIMULACIÓN", type="primary")

# --- EJECUCIÓN ---
if btn_run:
    sim = SimulacionMaster(TASA_BASE, TASA_SERVICIO, 1, MAX_SERVERS, UMBRAL_UP, UMBRAL_DOWN)
    
    with st.spinner("Procesando eventos discretos... (Calculando microsegundos)"):
        df_clientes, df_sistema, df_servidores = sim.correr()
        # Generar Dataset Maestro
        df_master = fusionar_realidad_vs_estimado(df_sistema, df_clientes)
        
    st.success("Simulación completada con éxito.")

    # --- PESTAÑAS DEL DASHBOARD ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Panorama Gerencial", 
        "📈 Real vs Estimado (Sesgos)", 
        "⚙️ Eficiencia Operativa", 
        "💾 Data Export"
    ])

    # === TAB 1: KPI Generales ===
    with tab1:
        st.subheader("Indicadores Clave de Desempeño (KPIs)")
        
        # Cálculos
        espera_media = df_clientes['Espera_Real_Min'].mean()
        espera_p95 = df_clientes['Espera_Real_Min'].quantile(0.95)
        recambios = sim.contador_activaciones + sim.contador_desactivaciones
        total_pax = len(df_clientes)
        costo_promedio = df_master['Servidores_Activos'].mean()
        
        # Tarjetas Métricas
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tiempo Espera Promedio", f"{espera_media:.2f} min", delta="Objetivo < 15min", delta_color="inverse")
        c2.metric("Peor Caso (95%)", f"{espera_p95:.2f} min", help="El 5% de los clientes esperó más que esto")
        c3.metric("Recambios de Turno", f"{recambios}", help="Total de veces que se prendió/apagó un cajero")
        c4.metric("Costo Medio (Cajeros)", f"{costo_promedio:.1f}", help="Promedio de personal activo durante el día")
        
        st.divider()
        
        st.subheader("Dinámica del Día (Hora Pico)")
        # Gráfico principal combinado
        fig_main = go.Figure()
        
        # Área de Cola
        fig_main.add_trace(go.Scatter(
            x=df_master.index, y=df_master['Cola'],
            name="Personas en Cola", fill='tozeroy', 
            line=dict(color='rgba(0,0,255,0.5)', width=1)
        ))
        
        # Línea de Capacidad (Cajeros)
        fig_main.add_trace(go.Scatter(
            x=df_master.index, y=df_master['Servidores_Activos'],
            name="Cajeros Activos", mode='lines',
            line=dict(color='red', width=3, shape='hv'), # hv = step chart
            yaxis='y2'
        ))
        
        fig_main.update_layout(
            title="Reacción de la Flota ante la Demanda",
            xaxis_title="Horario",
            yaxis=dict(title="Clientes en Espera"),
            yaxis2=dict(title="Cajeros Activos", overlaying='y', side='right'),
            hovermode="x unified",
            height=450
        )
        st.plotly_chart(fig_main, use_container_width=True)

    # === TAB 2: Análisis de Sesgo ===
    with tab2:
        st.subheader("Auditoría del Algoritmo: Realidad vs Estimación")
        st.markdown("""
        Este gráfico responde a la pregunta: **¿Qué tan precisa es nuestra estimación de espera?**
        - **Línea Azul:** Lo que la pantalla del banco le dice al cliente ("Espere 5 min").
        - **Línea Roja:** Lo que el cliente realmente esperó.
        """)
        
        fig_bias = go.Figure()
        fig_bias.add_trace(go.Scatter(x=df_master.index, y=df_master['Wait_Time_Estimado_Min'], name="Estimado (Ex-Ante)", line=dict(dash='dot')))
        fig_bias.add_trace(go.Scatter(x=df_master.index, y=df_master['Espera_Real_Min'], name="Real (Ex-Post)", line=dict(color='red')))
        
        fig_bias.update_layout(title="Serie de Tiempo: Sesgo de Predicción", yaxis_title="Minutos")
        st.plotly_chart(fig_bias, use_container_width=True)
        
        st.info(f"**Análisis de Sesgo:** En promedio, el sistema tiene un error de **{df_master['Sesgo_Algoritmo'].mean():.2f} minutos**. (Positivo = El cliente espera más de lo prometido).")

    # === TAB 3: Eficiencia ===
    with tab3:
        st.subheader("Utilización de Recursos")
        
        # Filtramos servidores que trabajaron
        df_active_srv = df_servidores[df_servidores['Horas_Activo'] > 0.01].copy()
        
        c1, c2 = st.columns([2,1])
        
        with c1:
            fig_util = px.bar(
                df_active_srv, x="ID", y="Utilizacion_Pct",
                color="Utilizacion_Pct", color_continuous_scale="RdYlGn_r",
                title="Porcentaje de Ocupación Real",
                range_y=[0, 100], text_auto='.1f'
            )
            fig_util.add_hline(y=85, line_dash="dash", annotation_text="Meta Eficiencia")
            st.plotly_chart(fig_util, use_container_width=True)
            
        with c2:
            st.write("#### Detalle por Cajero")
            st.dataframe(
                df_active_srv[['ID', 'Horas_Activo', 'Utilizacion_Pct']]
                .style.format({'Horas_Activo': '{:.2f} h', 'Utilizacion_Pct': '{:.1f}%'})
            )

    # === TAB 4: Datos ===
    with tab4:
        st.subheader("Descarga de Datasets")
        st.markdown("Descarga los datos procesados para análisis externo en Python/Excel/Tableau.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("###### Dataset Resumido (Minuto a Minuto)")
            st.dataframe(df_master.head())
            st.download_button("📥 Descargar Time-Series (CSV)", df_master.to_csv().encode('utf-8'), "timeseries_banco.csv")
            
        with col2:
            st.write("###### Registro Crudo de Clientes")
            st.dataframe(df_clientes.head())
            st.download_button("📥 Descargar Clientes Raw (CSV)", df_clientes.to_csv().encode('utf-8'), "clientes_raw.csv")

else:
    # Pantalla de bienvenida
    st.info("👈 Configura los parámetros en el menú lateral y presiona 'INICIAR SIMULACIÓN' para comenzar.")
    st.image("https://streamlit.io/images/brand/streamlit-mark-color.png", width=100)
    st.markdown("**Simulador desarrollado con Python + Streamlit + Plotly**")