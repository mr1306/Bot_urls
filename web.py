from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import plotly
import plotly.graph_objs as go
import json
import pandas as pd

app = Flask(__name__)
DB = "monitoreo.db" 

def get_data(query, params=()):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

@app.route("/")
def detalle():
    # Obtener parámetros de filtrado si existen
    servidor_filter = request.args.get('servidor', '')
    estado_filter = request.args.get('estado', '')
    fecha_filter = request.args.get('fecha', '')
    
    query = """
        SELECT servidor, fecha_hora, estado
        FROM registros_detalle
        WHERE 1=1
    """
    params = []
    
    if servidor_filter:
        query += " AND servidor LIKE ?"
        params.append(f'%{servidor_filter}%')
    
    if estado_filter:
        query += " AND estado = ?"
        params.append(estado_filter)
    
    if fecha_filter:
        query += " AND DATE(fecha_hora) = ?"
        params.append(fecha_filter)
    
    query += " ORDER BY fecha_hora DESC LIMIT 20"
    
    data = get_data(query, params)
    return render_template("detalle.html", data=data)

@app.route("/resumen")
def resumen():
    # Obtener parámetros de filtrado si existen
    servidor_filter = request.args.get('servidor', '')
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    periodo_grafico = request.args.get('periodo_grafico', '7d')  # Nuevo parámetro para el gráfico
    
    query = """
        SELECT servidor, fecha, estado_final
        FROM resumen_diario
        WHERE 1=1
    """
    params = []
    
    if servidor_filter:
        query += " AND servidor LIKE ?"
        params.append(f'%{servidor_filter}%')
    
    if fecha_inicio:
        query += " AND fecha >= ?"
        params.append(fecha_inicio)
    
    if fecha_fin:
        query += " AND fecha <= ?"
        params.append(fecha_fin)
    
    # Si no hay filtro de fecha, mostrar últimos 7 días por defecto
    if not fecha_inicio and not fecha_fin:
        default_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        query += " AND fecha >= ?"
        params.append(default_start)
    
    query += " ORDER BY fecha DESC, servidor"
    
    data = get_data(query, params)
    
    # Obtener lista única de servidores para el selector
    servidores_query = "SELECT DISTINCT servidor FROM resumen_diario ORDER BY servidor"
    servidores = [row[0] for row in get_data(servidores_query)]
    
    # Generar el gráfico con el período seleccionado
    plot_html = generar_grafico_estado_urls(periodo_grafico, fecha_inicio, fecha_fin)
    
    return render_template("resumen.html", 
                         data=data, 
                         servidores=servidores, 
                         plot_html=plot_html, 
                         periodo_actual=periodo_grafico,
                         fecha_inicio_actual=fecha_inicio,
                         fecha_fin_actual=fecha_fin)

def generar_grafico_estado_urls(periodo='7d', fecha_inicio=None, fecha_fin=None):
    """Genera un gráfico de estado de todas las URLs con período configurable"""
    
    # Determinar el rango de fechas según el período seleccionado o fechas personalizadas
    ahora = datetime.now()
    
    if fecha_inicio and fecha_fin:
        # Usar fechas personalizadas
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d') if fecha_fin else ahora
        titulo = f'Estado de URLs - {fecha_inicio} a {fecha_fin}'
        fecha_inicio_str = fecha_inicio_dt.strftime("%Y-%m-%d %H:%M:%S")
        fecha_fin_str = fecha_fin_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        query = """
            SELECT servidor, fecha_hora, estado
            FROM registros_detalle
            WHERE fecha_hora >= ? AND fecha_hora <= ?
            ORDER BY fecha_hora, servidor
        """
        params = (fecha_inicio_str, fecha_fin_str)
        
    else:
        # Usar período predefinido (quitamos 1m, 3m y 2y)
        if periodo == '7d':
            fecha_inicio_dt = ahora - timedelta(days=7)
            titulo = 'Estado de URLs - Últimos 7 días'
        elif periodo == '6m':
            fecha_inicio_dt = ahora - timedelta(days=180)
            titulo = 'Estado de URLs - Últimos 6 meses'
        elif periodo == '1y':
            fecha_inicio_dt = ahora - timedelta(days=365)
            titulo = 'Estado de URLs - Último año'
        else:
            fecha_inicio_dt = ahora - timedelta(days=7)
            titulo = 'Estado de URLs - Últimos 7 días'
        
        fecha_inicio_str = fecha_inicio_dt.strftime("%Y-%m-%d %H:%M:%S")
        fecha_fin_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
        
        query = """
            SELECT servidor, fecha_hora, estado
            FROM registros_detalle
            WHERE fecha_hora >= ?
            ORDER BY fecha_hora, servidor
        """
        params = (fecha_inicio_str,)
    
    data = get_data(query, params)
    
    if not data:
        return "<p>No hay datos disponibles para generar el gráfico</p>"
    
    # Convertir a DataFrame
    df = pd.DataFrame(data, columns=['servidor', 'fecha_hora', 'estado'])
    df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
    
    # Obtener lista única de servidores
    servidores = sorted(df['servidor'].unique())
    
    # Abreviar nombres de servidores largos
    def abreviar_nombre(nombre):
        if len(nombre) > 25:
            if '//' in nombre:
                # Para URLs, quedarse con el dominio principal
                partes = nombre.split('//')
                if len(partes) > 1:
                    dominio = partes[1].split('/')[0]
                    return dominio[:25] + '...' if len(dominio) > 25 else dominio
            return nombre[:22] + '...'
        return nombre
    
    servidores_abreviados = [abreviar_nombre(s) for s in servidores]
    
    # Crear el gráfico con Plotly
    fig = go.Figure()
    
    # Colores para cada servidor
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]
    
    # Espaciado compacto entre líneas
    espaciado = 0.7
    
    for i, servidor in enumerate(servidores):
        color = colors[i % len(colors)]
        y_pos = i * espaciado
        
        # Filtrar datos para este servidor
        servidor_data = df[df['servidor'] == servidor].copy()
        servidor_data = servidor_data.sort_values('fecha_hora')
        
        # Crear arrays para los datos
        x_vals = []
        y_vals = []
        custom_data = []
        
        # Procesar cada registro
        for _, row in servidor_data.iterrows():
            x_vals.append(row['fecha_hora'])
            # UP = posición alta, DOWN = posición baja
            y_vals.append(y_pos + (0.6 if row['estado'] == 'UP' else 0.2))
            custom_data.append(row['estado'])
        
        # Agregar la línea al gráfico
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode='lines+markers',
            name=servidor,
            line=dict(color=color, width=2.5),
            marker=dict(size=4, symbol='circle'),
            hovertemplate=(
                '<b>Servidor:</b> ' + servidor + '<br>' +
                '<b>Fecha/Hora:</b> %{x|%Y-%m-%d %H:%M:%S}<br>' +
                '<b>Estado:</b> %{customdata}<br>' +
                '<extra></extra>'
            ),
            customdata=custom_data,
            showlegend=False
        ))
    
    # Formato del eje X según el período
    if fecha_inicio and fecha_fin:
        # Para rangos personalizados, determinar formato basado en la duración
        if fecha_inicio_dt and fecha_fin_dt:
            duracion_dias = (fecha_fin_dt - fecha_inicio_dt).days
            if duracion_dias <= 7:
                tickformat = '%m-%d %H:%M'
            elif duracion_dias <= 30:
                tickformat = '%m-%d'
            else:
                tickformat = '%Y-%m-%d'
        else:
            tickformat = '%Y-%m-%d'
    elif periodo in ['7d', '1m']:
        tickformat = '%m-%d %H:%M'  # Mostrar día y hora para períodos cortos
    else:
        tickformat = '%Y-%m-%d'  # Solo fecha para períodos largos
    
    # Personalizar el diseño del gráfico
    fig.update_layout(
        title=dict(
            text=titulo,
            font=dict(size=16),
            x=0.5
        ),
        xaxis=dict(
            title='Fecha',
            tickformat=tickformat,
            gridcolor='lightgray',
            tickangle=45,
            rangeslider=dict(visible=False),
            tickfont=dict(size=9)
        ),
        yaxis=dict(
            title=dict(text='Servidores', font=dict(size=11)),
            tickmode='array',
            tickvals=[i * espaciado + 0.4 for i in range(len(servidores))],
            ticktext=servidores_abreviados,
            range=[-0.2, len(servidores) * espaciado - 0.2],
            gridcolor='lightgray',
            zeroline=False,
            tickfont=dict(size=9)
        ),
        hovermode='closest',
        # Dimensiones ajustadas
        width=1200,
        height=300 + len(servidores) * 15,
        showlegend=False,
        template='plotly_white',
        margin=dict(l=160, r=30, t=50, b=70),
        plot_bgcolor='rgba(240, 240, 240, 0.3)',
        paper_bgcolor='rgba(255, 255, 255, 0.9)'
    )
    
    # Agregar áreas sombreadas para mejor visualización
    for i in range(len(servidores)):
        fig.add_hrect(
            y0=i * espaciado,
            y1=(i + 1) * espaciado,
            fillcolor="lightgray" if i % 2 == 0 else "white",
            opacity=0.1,
            line_width=0
        )
    
    return fig.to_html(full_html=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)