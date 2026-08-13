import streamlit as st
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
import unicodedata

st.set_page_config(
    page_title="Conciliador de Mídia",
    page_icon="📊",
    layout="wide"
)

# Dicionário de Sinônimos / De-Para (Adicione mais se necessário)
SINONIMOS_PROGRAMAS = {
    "PIPP": ["PIPP", "PRIMEIRO IMPACTO", "PRIMEIRO IMPACTO PE"],
    "JN": ["JN", "JORNAL NACIONAL"],
    "BDPE": ["BDPE", "BOM DIA PE", "BOM DIA PERNAMBUCO"],
    "GE": ["GE", "GLOBO ESPORTE"],
    "CFT": ["CFT", "CALDEIRAO", "CALDEIRAO COM MION"]
}

def limpar_texto(texto, remover_espacos_totais=False):
    if not texto or pd.isna(texto):
        return ""
    texto = str(texto).upper().strip()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    if remover_espacos_totais:
        texto = re.sub(r'[^A-Z0-9]', '', texto)
    else:
        texto = re.sub(r'\s+', ' ', texto)
    return texto

def obter_variacoes_programa(programa_ap):
    prog_limpo = limpar_texto(programa_ap)
    for chave, variacoes in SINONIMOS_PROGRAMAS.items():
        if prog_limpo == chave or prog_limpo in [limpar_texto(v) for v in variacoes]:
            return [limpar_texto(v, remover_espacos_totais=True) for v in variacoes]
    return [limpar_texto(prog_limpo, remover_espacos_totais=True)]

def extrair_qtd_inteligente(linha):
    linha_sem_horario = re.sub(r'\b\d{1,2}:\d{2}(:\d{2})?\b', '', linha)
    numeros = re.findall(r'\b\d+\b', linha_sem_horario)
    numeros_validos = [int(n) for n in numeros if int(n) < 1000]
    if numeros_validos:
        return numeros_validos[-1]
    return 1

st.title("📊 Conciliador de Mídia - 3 Vias")
st.markdown("Faça o upload dos 3 PDFs da campanha para gerar a auditoria automática de faturamento.")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. AP (Matriz)")
    arquivo_ap = st.file_uploader("Envie a Autorização de Patrocínio", type=["pdf"], key="ap")

with col2:
    st.subheader("2. Mapa (Veículo)")
    arquivo_mapa = st.file_uploader("Envie o Mapa (Digital ou Escaneado)", type=["pdf"], key="mapa")

with col3:
    st.subheader("3. Auditoria (Comprovação)")
    arquivo_auditoria = st.file_uploader("Envie o relatório de Auditoria", type=["pdf"], key="auditoria")

st.divider()

if st.button("🔍 Conciliar Mídia", type="primary", use_container_width=True):
    if not (arquivo_ap and arquivo_mapa and arquivo_auditoria):
        st.error("⚠️ Por favor, faça o upload dos **3 arquivos** antes de prosseguir.")
    else:
        with st.spinner("Processando documentos e executando inteligência de conciliação... Aguarde..."):
            try:
                # 1. PROCESSANDO AP (Extração com Regex no que estiver dentro de parênteses)
                dados_ap = []
                with pdfplumber.open(arquivo_ap) as pdf:
                    for pagina in pdf.pages:
                        texto_pag = pagina.extract_text()
                        if texto_pag:
                            for linha in texto_pag.split('\n'):
                                # Filtra linhas válidas de programas
                                if "FONE" not in linha and "CLIENTE" not in linha and "COLOCACAO" not in linha:
                                    # Procura texto dentro de parênteses
                                    match_parenteses = re.search(r'\((.*?)\)', linha)
                                    if match_parenteses:
                                        nome_prog = match_parenteses.group(1).strip()
                                    else:
                                        # Se não houver parênteses, pega o texto antes dos números
                                        nome_prog = re.sub(r'\d.*', '', linha).strip()

                                    numeros = re.findall(r'\b\d+\b', linha)
                                    if numeros and len(nome_prog) > 2:
                                        qtd = int(numeros[-1])
                                        if qtd < 500: # Ignora códigos de 4 dígitos ou anos
                                            dados_ap.append({"Programa": nome_prog, "Qtd_AP": qtd})

                tabela_ap = pd.DataFrame(dados_ap)
                if not tabela_ap.empty:
                    tabela_ap["Programa_Exibicao"] = tabela_ap["Programa"].apply(lambda x: limpar_texto(x, False))
                    tabela_ap["Programa_Comparacao"] = tabela_ap["Programa"].apply(lambda x: limpar_texto(x, True))
                    tabela_ap = tabela_ap.groupby(["Programa_Exibicao", "Programa_Comparacao"], as_index=False)["Qtd_AP"].sum()
                else:
                    st.warning("⚠️ Nenhum programa válido foi identificado na AP. Verifique o layout do PDF.")
                    st.stop()

                programas_ap_map = dict(zip(tabela_ap["Programa_Comparacao"], tabela_ap["Programa_Exibicao"]))

                # 2. PROCESSANDO MAPA
                doc = fitz.open(stream=arquivo_mapa.read(), filetype="pdf")
                texto_mapa = ""
                for num_pagina in range(len(doc)):
                    pix = doc[num_pagina].get_pixmap(dpi=300)
                    img = Image.open(io.BytesIO(pix.tobytes()))
                    texto_mapa += pytesseract.image_to_string(img, lang='por') + "\n"

                dados_mapa = []
                for linha in texto_mapa.split('\n'):
                    linha_comparacao = limpar_texto(linha, remover_espacos_totais=True)
                    for prog_comp, prog_exib in programas_ap_map.items():
                        variacoes = obter_variacoes_programa(prog_comp)
                        if any(v in linha_comparacao for v in variacoes):
                            qtd = extrair_qtd_inteligente(linha)
                            dados_mapa.append({"Programa_Exibicao": prog_exib, "Qtd_Mapa": qtd})

                tabela_mapa = pd.DataFrame(dados_mapa)
                if not tabela_mapa.empty:
                    tabela_mapa = tabela_mapa.groupby("Programa_Exibicao", as_index=False)["Qtd_Mapa"].sum()
                else:
                    tabela_mapa = pd.DataFrame(columns=["Programa_Exibicao", "Qtd_Mapa"])

                # 3. PROCESSANDO AUDITORIA
                dados_auditoria = []
                with pdfplumber.open(arquivo_auditoria) as pdf:
                    for pagina in pdf.pages:
                        texto_pag = pagina.extract_text()
                        if texto_pag:
                            for linha in texto_pag.split('\n'):
                                linha_comparacao = limpar_texto(linha, remover_espacos_totais=True)
                                for prog_comp, prog_exib in programas_ap_map.items():
                                    variacoes = obter_variacoes_programa(prog_comp)
                                    if any(v in linha_comparacao for v in variacoes):
                                        qtd = extrair_qtd_inteligente(linha)
                                        dados_auditoria.append({"Programa_Exibicao": prog_exib, "Qtd_Auditoria": qtd})

                tabela_auditoria = pd.DataFrame(dados_auditoria)
                if not tabela_auditoria.empty:
                    tabela_auditoria = tabela_auditoria.groupby("Programa_Exibicao", as_index=False)["Qtd_Auditoria"].sum()
                else:
                    tabela_auditoria = pd.DataFrame(columns=["Programa_Exibicao", "Qtd_Auditoria"])

                # 4. CRUZAMENTO
                df_final = pd.merge(tabela_ap[["Programa_Exibicao", "Qtd_AP"]], tabela_mapa, on="Programa_Exibicao", how="left").fillna(0)
                df_final = pd.merge(df_final, tabela_auditoria, on="Programa_Exibicao", how="left").fillna(0)

                df_final.rename(columns={"Programa_Exibicao": "Programa"}, inplace=True)
                df_final["Erro_Veiculo"] = df_final["Qtd_AP"] - df_final["Qtd_Mapa"]
                df_final["Erro_Auditoria"] = df_final["Qtd_AP"] - df_final["Qtd_Auditoria"]

                # RESULTADOS
                erros = df_final[(df_final["Erro_Veiculo"] != 0) | (df_final["Erro_Auditoria"] != 0)]

                if erros.empty:
                    st.success("✅ **TUDO OK PARA FATURAR!** Nenhuma divergência encontrada na conciliação.")
                else:
                    st.error("❌ **DIVERGÊNCIA ENCONTRADA!** Confira as diferenças abaixo:")
                    st.dataframe(erros[["Programa", "Qtd_AP", "Qtd_Mapa", "Qtd_Auditoria"]], use_container_width=True)

                st.subheader("📋 Tabela Completa do Cruzamento")
                st.dataframe(df_final, use_container_width=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Conciliacao')
                
                st.download_button(
                    label="📥 Baixar Relatório em Excel",
                    data=buffer.getvalue(),
                    file_name="Relatorio_Conciliacao_Midia.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error(f"❌ Ocorreu um erro ao processar os arquivos: {e}")
