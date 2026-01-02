import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os
import re

# Configuração da Página
st.set_page_config(page_title="Sniper HA - Análise Consolidada", layout="wide")

# ==============================================================================
# 1. CARREGAMENTO E LIMPEZA DE DADOS
# ==============================================================================
@st.cache_data
def load_data():
    csv_file = 'MEGA_BASE_HA_COMPLETA.csv'
    
    if os.path.exists(csv_file):
        try:
            # Lê o CSV como string primeiro para tratar as vírgulas
            df = pd.read_csv(csv_file, dtype=str)
            
            # 1. Converter colunas numéricas (Tratando vírgula por ponto)
            cols_to_fix = ['HG', 'AG', 'HA_Line', 'HA_Odd_H', 'HA_Odd_A', 'Odd_H', 'Odd_A']
            
            for col in cols_to_fix:
                if col in df.columns:
                    # Remove aspas, troca vírgula por ponto e converte
                    df[col] = df[col].str.replace('"', '', regex=False)
                    df[col] = df[col].str.replace(',', '.', regex=False)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 2. LIMPEZA DOS NOMES DAS COMPETIÇÕES (A Mágica da Consolidação)
            if 'Competicao' in df.columns:
                def limpar_nome_liga(nome):
                    if pd.isna(nome): return "Indefinido"
                    nome = str(nome)
                    
                    # Padrão: Remove sufixos de ano (ex: _2021, _2425, _2122)
                    # Remove 4 dígitos no final ou meio (anos completos)
                    nome = re.sub(r'[_\s-]?20\d{2}', '', nome)
                    # Remove 4 dígitos compactos (ex: 2425 para 2024/2025)
                    nome = re.sub(r'[_\s-]?\d{4}', '', nome)
                    # Remove padrões de temporada (ex: 20/21)
                    nome = re.sub(r'\d{2}/\d{2}', '', nome)
                    # Remove sufixos como _G1, _Inv, etc se houver
                    nome = re.sub(r'_G\d+', '', nome)
                    
                    # Limpa underscores e espaços extras
                    nome = nome.replace('_', ' ').strip()
                    return nome

                df['Liga_Ref'] = df['Competicao'].apply(limpar_nome_liga)
            else:
                st.error("Coluna 'Competicao' não encontrada.")
                return pd.DataFrame()

            # Converter Data
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

            return df
        except Exception as e:
            st.error(f"Erro ao processar CSV: {e}")
            return None
    else:
        return None

# ==============================================================================
# 2. CÁLCULO DE LUCRO (HANDICAP ASIÁTICO)
# ==============================================================================
def calculate_pl(row, side, line_selected):
    # Se faltar dado essencial, retorna nulo
    if pd.isna(row['HA_Line']) or pd.isna(row['HA_Odd_H']) or pd.isna(row['HA_Odd_A']):
        return None

    hg, ag = row['HG'], row['AG']
    
    # Lógica: O DB sempre traz a linha do Mandante (HA_Line).
    # Se aposto no Mandante, uso a linha direta.
    # Se aposto no Visitante, a linha efetiva é o inverso.
    
    if side == 'Mandante':
        odd = row['HA_Odd_H']
        diff = hg - ag + line_selected 
    else: # Visitante
        odd = row['HA_Odd_A']
        # Ex: Escolhi Visitante -0.5. Preciso que o Mandante seja +0.5.
        # (AG - HG) - (-0.5) => AG - HG + 0.5.
        diff = (ag - hg) - line_selected 

    stake = 1.0
    
    # Regras matemáticas do HA
    if diff > 0.25: return (odd - 1) * stake       # Green
    elif diff < -0.25: return -stake               # Red
    elif abs(diff) < 0.01: return 0.0              # Void
    elif diff > 0: return ((odd - 1) * stake) / 2  # Half-Win
    else: return -stake / 2                        # Half-Loss

# ==============================================================================
# 3. INTERFACE E LÓGICA
# ==============================================================================
st.title("🎯 Sniper HA - Validador Consolidado")

df = load_data()

if df is None or df.empty:
    st.warning("⚠️ Arquivo 'MEGA_BASE_HA_COMPLETA.csv' não carregado corretamente.")
    st.stop()

# --- SIDEBAR (CONFIGURAÇÃO) ---
st.sidebar.header("⚙️ Configuração")

# 1. SELEÇÃO DE LIGA (CONSOLIDADA)
ligas_unicas = sorted(df['Liga_Ref'].unique())
liga_sel = st.sidebar.selectbox("Competição (Histórico Completo)", ligas_unicas)

# Cria o DF da liga (contendo TODAS as temporadas)
df_liga = df[df['Liga_Ref'] == liga_sel].copy()

# 2. SELEÇÃO DE LADO
lado_sel = st.sidebar.radio("Apostar em:", ['Mandante', 'Visitante'])

# 3. SELEÇÃO DE LINHA (COM MEMÓRIA PARA NÃO RESETAR)
# Descobre quais linhas existem nessa liga
available_lines = sorted(df_liga['HA_Line'].dropna().unique())

# Se for visitante, inverte o sinal para mostrar ao usuário a linha correta
if lado_sel == 'Visitante':
    display_lines = sorted([-x for x in available_lines])
else:
    display_lines = available_lines

if not display_lines:
    st.warning("Sem dados de Handicap para esta competição.")
    st.stop()

# Tenta recuperar a última escolha da memória
last_choice = st.session_state.get('last_line_choice', -0.5)

# Tenta achar o índice da última escolha na nova lista
try:
    current_index = display_lines.index(last_choice)
except ValueError:
    # Se não achar, tenta padrões (-0.5 ou 0.0)
    if -0.5 in display_lines: current_index = display_lines.index(-0.5)
    elif 0.0 in display_lines: current_index = display_lines.index(0.0)
    else: current_index = 0

linha_sel = st.sidebar.selectbox("Linha de Handicap", display_lines, index=current_index)
st.session_state['last_line_choice'] = linha_sel

st.sidebar.markdown("---")
btn_rodar = st.sidebar.button("🚀 Processar Dados", type="primary")

# ==============================================================================
# 4. PROCESSAMENTO E EXIBIÇÃO
# ==============================================================================

# Controle de Estado para manter os dados na tela
if btn_rodar:
    st.session_state['run_analysis'] = True

if st.session_state.get('run_analysis'):

    # 1. PREPARAR FILTRO
    # Precisamos traduzir a linha escolhida pelo usuário para a linha do DB (Base Home)
    if lado_sel == 'Mandante':
        db_target = linha_sel
        odd_col = 'HA_Odd_H'
    else:
        # Se usuário quer Visitante -0.5, no DB (Home) isso é +0.5
        db_target = linha_sel * -1 
        odd_col = 'HA_Odd_A'

    # 2. FILTRAR JOGOS
    # Filtramos onde HA_Line é igual ao nosso alvo
    df_f = df_liga[df_liga['HA_Line'] == db_target].copy()

    if df_f.empty:
        st.info(f"Nenhum jogo encontrado para {liga_sel} com a linha {linha_sel}.")
    else:
        # 3. CALCULAR P/L
        df_f['PL'] = df_f.apply(lambda row: calculate_pl(row, lado_sel, linha_sel), axis=1)
        df_f = df_f.dropna(subset=['PL'])

        if df_f.empty:
            st.warning("Jogos encontrados, mas sem odds válidas para cálculo.")
        else:
            # Ordenar por data para gráfico
            df_f = df_f.sort_values('Date')
            df_f['Acumulado'] = df_f['PL'].cumsum()

            # --- DASHBOARD ---
            st.markdown(f"### 📊 Resultado: {liga_sel}")
            st.caption(f"Estratégia: **{lado_sel} {linha_sel}** | Base consolidada.")

            # Métricas Globais
            total_jogos = len(df_f)
            total_lucro = df_f['PL'].sum()
            roi_global = (total_lucro / total_jogos) * 100
            odd_media = df_f[odd_col].mean()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Jogos Totais", total_jogos)
            c2.metric("Lucro (u)", f"{total_lucro:.2f}", delta_color="normal")
            c3.metric("ROI Global", f"{roi_global:.2f}%", delta=f"{roi_global:.2f}%")
            c4.metric("Odd Média", f"{odd_media:.2f}")

            st.divider()

            # --- TABELA POR TEMPORADA (AQUI ESTÁ A SOLUÇÃO) ---
            st.subheader("📅 Detalhe Temporada a Temporada")
            
            if 'Temporada' in df_f.columns:
                # Agrupa por temporada
                resumo = df_f.groupby('Temporada').agg(
                    Jogos=('PL', 'count'),
                    Lucro=('PL', 'sum'),
                    ROI=('PL', 'mean'),
                    Odd_Med=(odd_col, 'mean')
                ).reset_index()

                # Ordena (Mais recente primeiro)
                resumo = resumo.sort_values('Temporada', ascending=False)
                
                # Formatação Visual
                resumo_show = resumo.copy()
                resumo_show['ROI'] = (resumo_show['ROI'] * 100).round(2).astype(str) + '%'
                resumo_show['Lucro'] = resumo_show['Lucro'].round(2)
                resumo_show['Odd_Med'] = resumo_show['Odd_Med'].round(2)

                st.dataframe(
                    resumo_show,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Temporada": st.column_config.TextColumn("Temporada"),
                        "Jogos": st.column_config.NumberColumn("Qtd Jogos", format="%d"),
                        "Lucro": st.column_config.NumberColumn("Lucro (u)", format="%.2f"),
                        "ROI": st.column_config.TextColumn("ROI %"),
                        "Odd_Med": st.column_config.NumberColumn("Odd Média", format="%.2f")
                    }
                )
            else:
                st.warning("Coluna 'Temporada' não identificada na base.")

            st.divider()

            # --- GRÁFICO ---
            st.subheader("📈 Curva de Lucro Acumulado")
            fig = px.line(df_f, x='Date', y='Acumulado', markers=False)
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            fig.update_layout(xaxis_title="Data", yaxis_title="Lucro (Unidades)")
            st.plotly_chart(fig, use_container_width=True)

else:
    if not btn_rodar:
        st.info("👈 Configure os filtros na barra lateral e clique em 'Processar Dados'.")
