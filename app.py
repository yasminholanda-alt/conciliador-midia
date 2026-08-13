import unicodedata

# Função para padronizar os nomes e evitar divergências por digitação/OCR
def limpar_nome_programa(texto):
    if not texto:
        return ""
    # Transforma em maiúsculas e remove espaços extras nas pontas
    texto = str(texto).upper().strip()
    # Remove acentos
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    # Substitui múltiplos espaços por um único espaço
    texto = re.sub(r'\s+', ' ', texto)
    return texto

# --- DENTRO DO SEU CÓDIGO DE PROCESSAMENTO ---
# Aplique essa limpeza logo após extrair as tabelas:

# 1. Padroniza AP
tabela_ap["Programa"] = tabela_ap["Programa"].apply(limpar_nome_programa)
tabela_ap = tabela_ap.groupby("Programa", as_index=False).sum()

# 2. Padroniza Mapa
tabela_mapa["Programa"] = tabela_mapa["Programa"].apply(limpar_nome_programa)
tabela_mapa = tabela_mapa.groupby("Programa", as_index=False).sum()

# 3. Padroniza Auditoria
tabela_auditoria["Programa"] = tabela_auditoria["Programa"].apply(limpar_nome_programa)
tabela_auditoria = tabela_auditoria.groupby("Programa", as_index=False).sum()

# Cruzamento oficial dos dados padronizados
df_final = pd.merge(tabela_ap, tabela_mapa, on="Programa", how="outer").fillna(0)
df_final = pd.merge(df_final, tabela_auditoria, on="Programa", how="outer").fillna(0)
