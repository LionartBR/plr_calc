# streamlit_app.py
import streamlit as st
from pathlib import Path
import base64
# importa do seu calc.py
from calc import calcular_plr, parse_brl, format_brl, PLRConfig


# -------- Helpers --------
def format_bi(valor_bi: float) -> str:
    inteiro, cent = divmod(int(round(valor_bi * 100)), 100)
    s_int = f"{inteiro:,}".replace(",", ".")
    return f"R$ {s_int},{cent:02d} bi"

def md_safe(text: str) -> str:
    return (text.replace("\\", "\\\\")
                .replace("$", "\\$")
                .replace("*", "\\*")
                .replace("_", "\\_"))

# -------- Parâmetros FIXOS (back) --------
N_FIXED = 89962
L_S1_BASE_BI = 8.9   # R$ bi (1º semestre base)
L_A_BASE_BI  = 15.9   # R$ bi (anual base)

# ----- Calibração (fixo no back) -----
ALPHA_S1_EFF = 0.02915   
BETA_A_EFF   = 0.06014   

MULTS = {"Pessimista": 0.8489, "Realista": 1.00, "Otimista": 1.3041}
REGRA_FIXA = "proporcional"

# --- Header: logo CAIXA em cima, título embaixo (com gap controlado) ---
ASSETS_DIR = Path(__file__).parent / "assets"
CAIXA_LOGO = ASSETS_DIR / "caixa_x.svg"   # ou .png
LOGO_WIDTH = 220  # ajuste o tamanho do logo (px)
GAP_PX = 6        # ajuste o espaço entre logo e título (px)

def render_header():
    if CAIXA_LOGO.exists():
        img_bytes = CAIXA_LOGO.read_bytes()
        b64 = base64.b64encode(img_bytes).decode("ascii")
        ext = CAIXA_LOGO.suffix.lstrip(".")  # 'svg' ou 'png'
        st.markdown(
            f"""
<div style="display:flex; flex-direction:column; align-items:center;">
  <img src="data:image/{ext};base64,{b64}"
       style="width:{LOGO_WIDTH}px; margin:0 0 {GAP_PX}px 0;" />
  <h1 style="margin:0;">PLR CAIXA 2025 SIMULADOR</h1>
</div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<h1 style='text-align:center;margin:0;'>PLR CAIXA 2025 SIMULADOR</h1>",
            unsafe_allow_html=True
        )

# chame isto logo após st.set_page_config(...)
render_header()

# -------- UI --------
st.set_page_config(page_title="PLR CAIXA 2025", page_icon="🧮", layout="centered")
st.caption("Escolha o cenário, informe seu salário (RB) e os meses trabalhados. O resultado será proporcional ao tempo trabalhado.")

with st.expander("Parâmetros usados (informativo)"):
    n_fmt = f"{N_FIXED:,}".replace(",", ".")
    ls1 = md_safe(format_bi(L_S1_BASE_BI))
    la  = md_safe(format_bi(L_A_BASE_BI))
    st.markdown(
        f"- **N (empregados):** `{n_fmt}`\n"
        f"- **Lucros base:** 1º semestre = `{ls1}`, anual = `{la}`\n"
        f"- **Multiplicadores:** Pessimista = `{MULTS['Pessimista']:.2f}`, Realista = `{MULTS['Realista']:.2f}`, Otimista = `{MULTS['Otimista']:.2f}`\n"
        f"- **Regra de redução no teto global (15%):** `{REGRA_FIXA}`"
    )

# -------- Formulário --------
with st.form("form-plr", clear_on_submit=False):
    c1, c2 = st.columns([2, 1.2])

    with c1:
        salario_str = st.text_input("Salário (Remuneração Base - RB)", placeholder="Ex.: R$ 1.234,56")
        meses_trab = st.number_input("Meses trabalhados (0–12)", min_value=0, max_value=12, step=1, value=12, format="%d")

    with c2:
        cenario_escolhido = st.radio("Cenário", ["Pessimista", "Realista", "Otimista"], horizontal=True, index=1)

    submit = st.form_submit_button("Calcular", use_container_width=True)

st.markdown("---")
st.subheader("Resultado")

if submit:
    erros = []
    try:
        S = parse_brl(salario_str)
        if S <= 0:
            erros.append("O salário deve ser maior que zero.")
    except Exception:
        erros.append("Não consegui entender o salário. Use algo como 'R$ 7.730,00'.")

    if erros:
        st.error(" • ".join(erros))
    else:
        # aplica multiplicador do cenário nos lucros
        mult = MULTS[cenario_escolhido]
        L_S1 = (L_S1_BASE_BI * mult) * 1e9
        L_A  = (L_A_BASE_BI  * mult) * 1e9

        # cálculo "cheio"
        cfg = PLRConfig(alpha_S1_eff=ALPHA_S1_EFF, beta_A_eff=BETA_A_EFF)
        r = calcular_plr(S=S, N=N_FIXED, L_S1=L_S1, L_A=L_A, cfg=cfg, regra_reducao_global=REGRA_FIXA)

        # -------- Proporcionalidade por meses --------
        m = int(meses_trab)
        fA  = m / 12.0            # fator anual
        fS1 = min(m, 6) / 6.0     # fator para o adiantamento (S1 tem 6 meses)
        adiant_exib = r["adiantamento"] * fS1
        total_exib  = r["total_anual"]  * fA
        segunda_exib = max(0.0, total_exib - adiant_exib)

        # Cabeçalho do cenário
        st.markdown(f"### Cenário **{cenario_escolhido}**")

        # Cards de destaque (já proporcionais)
        d1, d2, d3 = st.columns(3)
        d1.metric("Adiantamento (Set)",      format_brl(adiant_exib))
        d2.metric("Total anual (pós-teto)",  format_brl(total_exib))
        d3.metric("2ª parcela (Mar)", format_brl(segunda_exib))

        # Detalhamento
        with st.expander(f"Detalhamento — {cenario_escolhido}"):
            st.markdown(
                f"""
**Lucros usados**  
- 1º semestre: `{md_safe(format_bi(L_S1/1e9))}`  
- Anual: `{md_safe(format_bi(L_A/1e9))}`  

**Componentes (cálculo cheio, antes da proporcionalidade)**  
- Regra Básica anual (Fenaban): {format_brl(r["RB_ano"])}  
- Teto global (15% por empregado): {format_brl(r["T_global"])}  
- 2,2% anual (após cap): {format_brl(r["ADD_A_cap"])}  
- 4% Social anual (após garantia/cap): {format_brl(r["SOC_A_cap"])}  
- Total anual bruto (antes do teto): {format_brl(r["PLR_A_bruta"])}  
- Redução total pelo teto global: {format_brl(r["reducao_global_aplicada"])}  
- Adiantamento (S1) cheio: {format_brl(r["PLR_S1"])}

**Valores exibidos (após proporcionalidade)**  
- Adiantamento proporcional: {format_brl(adiant_exib)}  
- Total anual proporcional: {format_brl(total_exib)}  
- 2ª parcela proporcional: {format_brl(segunda_exib)}
                """
            )

st.markdown("---")
st.caption("Aplicamos: Regra Básica (Fenaban), 2,2% (teto individual), PLR Social (garantia de 1 salário no anual) e teto global de 15% (redução proporcional). Depois, proporcionalidade por meses trabalhados.")
