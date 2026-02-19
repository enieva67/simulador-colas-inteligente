import streamlit as st
import heapq
import random
from collections import deque
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ==========================================
# 1. DEFINICIÓN DE LA CURVA DE DEMANDA
# ==========================================

def curva_demanda_diaria(hora_actual_simulacion, tasa_base):
    """
    Define el patrón de llegadas según la hora del día.
    hora_actual_simulacion: va de 0.0 (Apertura) a 8.0 (Cierre)
    tasa_base: el multiplicador de volumen de gente (input del usuario)
    """
    # Patrón de ondas:
    # 0-2h: Calma (30% del tráfico)
    # 2-4h: Subida (80% del tráfico)
    # 4-6h: HORA PICO (150% del tráfico - Almuerzo)
    # 6-8h: Bajada (50% del tráfico)
    
    # Usamos funciones seno/coseno para hacerlo suave, o condiciones simples
    # Aquí usaré condiciones para que sea fácil de entender visualmente
    
    factor = 0.5 # Default
    
    if 0 <= hora_actual_simulacion < 2:
        factor = 0.4  # Mañana tranquila
    elif 2 <= hora_actual_simulacion < 4:
        factor = 1.0  # Media mañana normal
    elif 4 <= hora_actual_simulacion < 6:
        factor = 1.8  # HORA PICO (Explosión)
    elif 6 <= hora_actual_simulacion <= 8:
        factor = 0.6  # Tarde tranquila
        
    return tasa_base * factor

# ==========================================
# 2. LÓGICA DE SIMULACIÓN (Backend Modificado)
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

class SimulacionBancoVariable:
    def __init__(self, tasa_base, tasa_servicio, min_serv, max_serv, umbral_up, umbral_down):
        self.tasa_base = tasa_base # ESTO AHORA ES UN BASE, NO FIJO
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
        self.log_serie_tiempo = [] 

    def _get_tasa_actual(self):
        # Calculamos la tasa exacta en este milisegundo de simulación
        return curva_demanda_diaria(self.reloj, self.tasa_base)

    def _registrar_estado(self):
        activos = sum(1 for s in self.servidores if s.activo)
        self.log_serie_tiempo.append({
            'Tiempo': self.reloj,
            'Cola': len(self.cola_clientes),
            'Servidores Activos': activos,
            'Tasa Llegada Actual': self._get_tasa_actual() # Guardamos para graficar
        })

    def _calcular_ewt(self):
        activos = sum(1 for s in self.servidores if s.activo)
        if activos == 0: return 999.0
        return len(self.cola_clientes) / (activos * self.mu)

    def _gestionar_escalado(self, ewt_actual):
        activos = sum(1 for s in self.servidores if s.activo)
        # Lógica de histéresis idéntica
        if ewt_actual > self.umbral_up and activos < self.max_servers:
            for s in self.servidores:
                if not s.activo:
                    s.activo = True
                    return 
        elif ewt_actual < self.umbral_down and activos > self.min_servers:
            for i in range(self.max_servers - 1, -1, -1):
                s = self.servidores[i]
                if s.activo and not s.ocupado:
                    s.activo = False
                    return

    def programar_llegada(self):
        # === MAGIA DE TASA VARIABLE ===
        # Consultamos la tasa para el momento actual
        lambd_actual = self._get_tasa_actual()
        
        # Generamos el siguiente delta de tiempo
        # Nota: Si la tasa cambia drásticamente en el futuro inmediato, esto tiene un pequeño error,
        # pero para simulaciones paso a paso es una aproximación estándar muy válida.
        tiempo = random.expovariate(lambd_actual)
        
        proxima_llegada = self.reloj + tiempo
        
        # Solo programamos si estamos dentro del horario bancario (ej: 8 horas)
        if proxima_llegada <= 8.0:
            heapq.heappush(self.eventos, (proxima_llegada, "LLEGADA", None))

    def correr(self):
        self.programar_llegada()
        
        # Barra de progreso
        progress_bar = st.progress(0)
        
        while self.eventos:
            tiempo, tipo, data = heapq.heappop(self.eventos)
            
            # Si el evento ocurre después de las 8 horas, cerramos el banco (no entran mas, pero se atiende a los que quedan)
            if tipo == "LLEGADA" and tiempo > 8.0:
                continue
                
            self.reloj = tiempo
            
            if tipo == "LLEGADA":
                # Crear cliente
                c_id = len(self.historial_clientes) + len(self.cola_clientes)
                c = Cliente(c_id, self.reloj)
                c.largo_cola_al_llegar = len(self.cola_clientes)
                
                ewt = self._calcular_ewt()
                self._gestionar_escalado(ewt)
                
                self.cola_clientes.append(c)
                self._intentar_asignar()
                self.programar_llegada() # Programar siguiente
                self._registrar_estado()

            elif tipo == "SALIDA":
                srv_id = data
                self.servidores[srv_id].ocupado = False
                self._intentar_asignar()
                if not self.cola_clientes: self._gestionar_escalado(0.0)
                self._registrar_estado()
            
            # Actualizar barra (aprox sobre 8 horas)
            progress = min(self.reloj / 8.0, 1.0)
            progress_bar.progress(progress)

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
        # Igual que antes pero ordenado
        data_clientes = []
        for c in self.historial_clientes:
            espera = (c.hora_inicio_atencion - c.hora_llegada) * 60
            data_clientes.append({
                "Llegada (h)": c.hora_llegada,
                "Espera (min)": espera,
                "Cola al llegar": c.largo_cola_al_llegar
            })
        return pd.DataFrame(data_clientes), pd.DataFrame(self.log_serie_tiempo)

# ==========================================
# 3. INTERFAZ GRÁFICA (Streamlit)
# ==========================================

st.set_page_config(page_title="Simulador de Colas Dinámico", layout="wide")

st.title("🌊 Simulador de Colas con Demanda Variable (Hora Pico)")
st.markdown("""
A diferencia del anterior, aquí **la gente no llega siempre igual**.
Simulamos un día de 8 horas con **Hora Pico** a mitad del día. 
Observa cómo el algoritmo de Auto-Escalado lucha para adaptarse a la ola de clientes.
""")

with st.sidebar:
    st.header("⚙️ Configuración del Escenario")
    TASA_BASE = st.slider("Tasa Base (Clientes/Hora Normal)", 50, 300, 100)
    TASA_SERVICIO = st.slider("Velocidad Cajero (Clientes/Hora)", 10, 60, 20)
    
    st.subheader("Capacidad")
    MAX_SERVERS = st.slider("Máximo de Cajeros Disponibles", 5, 30, 15)
    
    st.subheader("Reglas de Reacción")
    UMBRAL_UP = st.number_input("Activar si espera > (min)", 5, 60, 15)
    
    run_btn = st.button("▶️ Simular Día Completo", type="primary")

if run_btn:
    sim = SimulacionBancoVariable(
        TASA_BASE, TASA_SERVICIO, 1, MAX_SERVERS, UMBRAL_UP, 5.0
    )
    
    with st.spinner('Simulando 8 horas de operación bancaria...'):
        df_clientes, df_tiempo = sim.correr()

    # MÉTRICAS
    col1, col2, col3 = st.columns(3)
    col1.metric("Clientes Atendidos", len(df_clientes))
    col2.metric("Espera Promedio", f"{df_clientes['Espera (min)'].mean():.2f} min")
    col3.metric("Espera Máxima", f"{df_clientes['Espera (min)'].max():.2f} min")

    st.divider()
    
    # GRÁFICO MAESTRO
    st.subheader("🔥 El 'Incendio' de la Hora Pico")
    st.caption("Verde: Demanda de Clientes (La Ola) | Rojo: Cajeros respondiendo | Azul: La Cola resultante")
    
    fig = go.Figure()
    
    # 1. La Curva de Demanda (Lo que genera el problema)
    fig.add_trace(go.Scatter(
        x=df_tiempo["Tiempo"], y=df_tiempo["Tasa Llegada Actual"],
        name="Demanda (Clientes/Hora)", line=dict(color='green', width=1, dash='dot'),
        yaxis="y2"
    ))
    
    # 2. La Respuesta (Cajeros)
    fig.add_trace(go.Scatter(
        x=df_tiempo["Tiempo"], y=df_tiempo["Servidores Activos"],
        name="Cajeros Activos", line=dict(color='red', width=3),
        mode='lines'
    ))
    
    # 3. La Consecuencia (Cola)
    fig.add_trace(go.Scatter(
        x=df_tiempo["Tiempo"], y=df_tiempo["Cola"],
        name="Personas en Cola", line=dict(color='blue', width=1),
        fill='tozeroy', fillcolor='rgba(0,0,255,0.1)'
    ))
    
    fig.update_layout(
        height=500,
        xaxis_title="Horas del Día (0 = Apertura, 4 = Hora Pico)",
        yaxis=dict(title="Cantidad (Personas / Cajeros)"),
        yaxis2=dict(title="Tasa de Llegada (Intensidad)", overlaying="y", side="right", showgrid=False),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Scatter de Espera vs Hora
    st.subheader("🕒 ¿A qué hora sufrió más la gente?")
    fig_scatter = px.scatter(df_clientes, x="Llegada (h)", y="Espera (min)", 
                             color="Espera (min)", color_continuous_scale="RdYlGn_r",
                             title="Tiempos de Espera por Hora de Llegada")
    st.plotly_chart(fig_scatter, use_container_width=True)