import streamlit as st
import heapq
import random
from collections import deque
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 1. LÓGICA DE SIMULACIÓN (Backend)
# ==========================================

class Cliente:
    def __init__(self, id_cliente, hora_llegada):
        self.id = id_cliente
        self.hora_llegada = hora_llegada
        self.hora_inicio_atencion = None
        self.hora_salida = None
        self.largo_cola_al_llegar = 0

class Servidor:
    def __init__(self, id_servidor):
        self.id = id_servidor
        self.activo = False
        self.ocupado = False
        self.tiempo_fin_servicio = 0.0

class SimulacionBancoInteligente:
    def __init__(self, tasa_llegada, tasa_servicio, min_serv, max_serv, umbral_up, umbral_down):
        self.lambd = tasa_llegada
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
        
        # LOGS PARA GRAFICAR
        # Guardaremos el estado cada vez que cambie algo importante
        self.log_serie_tiempo = [] 

    def _registrar_estado(self):
        activos = sum(1 for s in self.servidores if s.activo)
        ocupados = sum(1 for s in self.servidores if s.ocupado)
        cola = len(self.cola_clientes)
        self.log_serie_tiempo.append({
            'Tiempo': self.reloj,
            'Cola': cola,
            'Servidores Activos': activos,
            'Servidores Ocupados': ocupados
        })

    def _calcular_ewt(self):
        activos = sum(1 for s in self.servidores if s.activo)
        if activos == 0: return 999.0
        return len(self.cola_clientes) / (activos * self.mu)

    def _gestionar_escalado(self, ewt_actual):
        activos = sum(1 for s in self.servidores if s.activo)
        
        # Lógica de histéresis
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            for s in self.servidores:
                if not s.activo:
                    s.activo = True
                    return 
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            # Desactivar uno que esté libre (desde el último)
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    s.activo = False
                    return

    def programar_llegada(self):
        tiempo = random.expovariate(self.lambd)
        heapq.heappush(self.eventos, (self.reloj + tiempo, "LLEGADA", None))

    def correr(self, num_clientes):
        self.programar_llegada()
        clientes_creados = 0
        clientes_procesados = 0
        
        # Barra de progreso en Streamlit
        progress_bar = st.progress(0)
        
        while clientes_procesados < num_clientes or len(self.eventos) > 0:
            if not self.eventos: break
            
            tiempo, tipo, data = heapq.heappop(self.eventos)
            self.reloj = tiempo
            
            if tipo == "LLEGADA":
                if clientes_creados < num_clientes:
                    c = Cliente(clientes_creados, self.reloj)
                    clientes_creados += 1
                    
                    c.largo_cola_al_llegar = len(self.cola_clientes)
                    ewt = self._calcular_ewt()
                    self._gestionar_escalado(ewt)
                    
                    self.cola_clientes.append(c)
                    self._intentar_asignar()
                    self.programar_llegada()
                    self._registrar_estado() # FOTO DEL SISTEMA

            elif tipo == "SALIDA":
                srv_id = data
                self.servidores[srv_id].ocupado = False
                clientes_procesados += 1
                
                self._intentar_asignar()
                if not self.cola_clientes: self._gestionar_escalado(0.0)
                self._registrar_estado() # FOTO DEL SISTEMA
                
                # Actualizar barra de progreso cada 10%
                if clientes_procesados % (num_clientes // 10) == 0:
                    progress_bar.progress(min(clientes_procesados / num_clientes, 1.0))

        progress_bar.empty()
        return self._generar_reportes()

    def _intentar_asignar(self):
        if not self.cola_clientes: return
        
        candidato = next((s for s in self.servidores if s.activo and not s.ocupado), None)
        if candidato:
            cliente = self.cola_clientes.popleft()
            candidato.ocupado = True
            cliente.hora_inicio_atencion = self.reloj
            duracion = random.expovariate(self.mu)
            cliente.hora_salida = self.reloj + duracion
            candidato.tiempo_fin_servicio = cliente.hora_salida
            
            self.historial_clientes.append(cliente)
            heapq.heappush(self.eventos, (cliente.hora_salida, "SALIDA", candidato.id))

    def _generar_reportes(self):
        # 1. DataFrame de Clientes
        data_clientes = []
        for c in self.historial_clientes:
            espera = (c.hora_inicio_atencion - c.hora_llegada) * 60 # Minutos
            total = (c.hora_salida - c.hora_llegada) * 60
            data_clientes.append({
                "ID": c.id,
                "Llegada (h)": c.hora_llegada,
                "Espera (min)": espera,
                "Tiempo Total (min)": total,
                "Cola al llegar": c.largo_cola_al_llegar
            })
        df_clientes = pd.DataFrame(data_clientes)
        
        # 2. DataFrame Temporal (Serie de tiempo)
        df_tiempo = pd.DataFrame(self.log_serie_tiempo)
        
        return df_clientes, df_tiempo

# ==========================================
# 2. INTERFAZ GRÁFICA (Streamlit)
# ==========================================

st.set_page_config(page_title="Simulador de Colas Inteligente", layout="wide")

st.title("🏦 Simulador de Optimización de Colas (Algoritmo M/M/c Dinámico)")
st.markdown("""
Esta aplicación simula un sistema de atención bancaria con **Auto-Escalado**.
El sistema abre o cierra cajas automáticamente basándose en el **Tiempo Estimado de Espera**.
""")

# --- SIDEBAR DE CONFIGURACIÓN ---
with st.sidebar:
    st.header("⚙️ Parámetros de Simulación")
    
    st.subheader("Tráfico")
    N_CLIENTES = st.number_input("Cantidad de Clientes", 1000, 10000, 2000, step=500)
    TASA_LLEGADA = st.slider("Clientes por Hora (Llegada)", 10, 200, 100)
    
    st.subheader("Capacidad")
    TASA_SERVICIO = st.slider("Capacidad por Cajero (Clientes/Hora)", 5, 50, 15)
    
    col1, col2 = st.columns(2)
    MIN_SERVERS = col1.number_input("Mín. Cajeros", 1, 5, 1)
    MAX_SERVERS = col2.number_input("Máx. Cajeros", 2, 20, 10)
    
    st.subheader("🤖 Reglas de Auto-Escalado")
    UMBRAL_UP = st.slider("Activar si espera estimada > (min)", 5, 60, 15)
    UMBRAL_DOWN = st.slider("Desactivar si espera estimada < (min)", 1, 30, 5)
    
    st.info(f"**Histéresis:** Se contrata personal si la espera supera {UMBRAL_UP} min. Se libera si baja de {UMBRAL_DOWN} min.")
    
    run_btn = st.button("▶️ Ejecutar Simulación", type="primary")

# --- EJECUCIÓN ---
if run_btn:
    sim = SimulacionBancoInteligente(
        TASA_LLEGADA, TASA_SERVICIO, MIN_SERVERS, MAX_SERVERS, UMBRAL_UP, UMBRAL_DOWN
    )
    
    with st.spinner('Procesando simulación matemática...'):
        df_clientes, df_tiempo = sim.correr(N_CLIENTES)

    # --- RESULTADOS KPI ---
    espera_promedio = df_clientes["Espera (min)"].mean()
    espera_max = df_clientes["Espera (min)"].max()
    activaciones_promedio = df_tiempo["Servidores Activos"].mean()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tiempo Espera Promedio", f"{espera_promedio:.2f} min")
    col2.metric("Tiempo Espera Máximo", f"{espera_max:.2f} min")
    col3.metric("Cajeros Activos (Promedio)", f"{activaciones_promedio:.1f}")
    col4.metric("Total Clientes Atendidos", f"{len(df_clientes)}")

    # --- GRÁFICOS INTERACTIVOS (PLOTLY) ---
    
    st.divider()
    
    # 1. GRÁFICO COMBINADO: COLA vs SERVIDORES
    st.subheader("📈 Respuesta del Sistema en Tiempo Real")
    st.caption("Observa cómo aumenta la línea ROJA (Cajeros) cuando sube la línea AZUL (Cola). Eso es el algoritmo trabajando.")
    
    # Creamos figura con doble eje Y
    fig_combo = go.Figure()
    
    # Línea de Cola (Eje Y izquierdo)
    fig_combo.add_trace(go.Scatter(
        x=df_tiempo["Tiempo"], y=df_tiempo["Cola"],
        name="Largo de Cola", mode='lines', line=dict(color='blue', width=1),
        fill='tozeroy', fillcolor='rgba(0,0,255,0.1)'
    ))
    
    # Línea de Servidores (Eje Y derecho)
    fig_combo.add_trace(go.Scatter(
        x=df_tiempo["Tiempo"], y=df_tiempo["Servidores Activos"],
        name="Cajeros Activos", mode='lines', line=dict(color='red', width=2, shape='hv'),
        yaxis="y2"
    ))
    
    fig_combo.update_layout(
        height=400,
        xaxis_title="Horas de Operación",
        yaxis=dict(title="Personas en Cola", showgrid=False),
        yaxis2=dict(title="Cajeros Activos", overlaying="y", side="right", showgrid=True),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig_combo, use_container_width=True)
    
    col_g1, col_g2 = st.columns(2)
    
    # 2. HISTOGRAMA
    with col_g1:
        st.subheader("📊 Distribución de Esperas")
        fig_hist = px.histogram(df_clientes, x="Espera (min)", nbins=50, 
                                title="¿Cuánto esperó la mayoría?", color_discrete_sequence=['#2E86C1'])
        fig_hist.add_vline(x=UMBRAL_UP, line_dash="dash", line_color="red", annotation_text="Umbral Activación")
        st.plotly_chart(fig_hist, use_container_width=True)
        
    # 3. SCATTER PLOT
    with col_g2:
        st.subheader("🕒 Espera vs. Hora de Llegada")
        fig_scatter = px.scatter(df_clientes, x="Llegada (h)", y="Espera (min)", 
                                 color="Cola al llegar", title="Saturación por Horario")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # --- DATOS RAW ---
    with st.expander("Ver Datos Crudos (Excel/CSV)"):
        st.dataframe(df_clientes)

else:
    st.info("👈 Ajusta los parámetros en el menú izquierdo y presiona 'Ejecutar'.")