from dataclasses import dataclass

# =========================
# Constantes 2025 (da imagem)
# =========================
FENABAN_FIXO_2025 = 3532.93
FENABAN_TETO_RB_2025 = 18952.48
FENABAN_TETO_RB_MAJORADA_2025 = 41695.41  # informativo
FENABAN_ADIC_TETO_2025 = 7336.62          # teto individual da parcela adicional FENABAN (2025)

# Parâmetros conhecidos CAIXA 2025
NUM_EMPREGADOS_2025 = 84_000
LUCRO_LIQUIDO_2025 = 6_500_000_000.00  # R$ 6,5 bi
INPC_ATE_AGO_2025 = 0.0568             # informativo (já refletido nos valores acima)

# =========================
# IR EXCLUSIVO DA PLR (2025)
# =========================
IR_PLR_TABELA_2025 = [
    (6677.55, 0.00,   0.00),
    (9922.28, 0.075,  500.82),
    (13167.00,0.15,  1244.99),
    (16380.38,0.225, 2232.51),
    (float("inf"),0.275,3051.53),  # topo
]

def ir_plr_2025(valor_bruto: float) -> float:
    for limite, aliq, ded in IR_PLR_TABELA_2025:
        if valor_bruto <= limite:
            imp = valor_bruto * aliq - ded
            return max(0.0, round(imp, 2))
    return 0.0

def ir_primeira_parcela_2025(bruto_setembro: float, bruto_marco_anterior: float) -> float:
    """IR 1ª parcela = IR(Março + Setembro) - IR(Março)."""
    total = bruto_marco_anterior + bruto_setembro
    return max(0.0, round(ir_plr_2025(total) - ir_plr_2025(bruto_marco_anterior), 2))

# =========================
# Modelo de entrada
# =========================
@dataclass
class EntradaCaixa2025:
    salario_base: float            # remuneração-base atual
    meses_trabalhados: int = 12    # 1..12
    plr_bruta_marco_2025: float = 0.0  # 2ª parcela (ano anterior) recebida em mar/2025 para compensação do IR

# =========================
# Núcleo do cálculo
# =========================
def calcular_plr_caixa_primeira_parcela_2025(e: EntradaCaixa2025) -> dict:
    # Proporcionalidade
    prop = max(0, min(e.meses_trabalhados, 12)) / 12.0

    # --- Módulo FENABAN ---
    # Regra Básica: 90% do salário + fixo (cap no teto RB 2025), depois proporcionalidade
    rb_sem_teto = 0.90 * e.salario_base + FENABAN_FIXO_2025
    rb_fenaban = min(rb_sem_teto, FENABAN_TETO_RB_2025) * prop

    # Parcela Adicional FENABAN: 2,2% do lucro ÷ nº empregados (cap no teto individual 2025), depois proporcionalidade
    adicional_unit = (LUCRO_LIQUIDO_2025 * 0.022) / NUM_EMPREGADOS_2025
    adicional_unit_capped = min(adicional_unit, FENABAN_ADIC_TETO_2025)
    adicional_fenaban = adicional_unit_capped * prop

    # --- PLR Social (CAIXA) ---
    plr_social_unit = (LUCRO_LIQUIDO_2025 * 0.04) / NUM_EMPREGADOS_2025
    plr_social = plr_social_unit * prop

    # Total antes do teto global
    total_plr = rb_fenaban + adicional_fenaban + plr_social

    # Teto global CAIXA: 3 remunerações-base por empregado
    total_pos_teto = min(total_plr, 3 * e.salario_base)

    # 1ª parcela (set/2025) = 50% do total pós-teto
    bruto_setembro = round(0.5 * total_pos_teto, 2)

    # IR e líquido
    ir_setembro = ir_primeira_parcela_2025(bruto_setembro, e.plr_bruta_marco_2025)
    liquido_setembro = round(bruto_setembro - ir_setembro, 2)

    return {
        "prop": prop,
        "rb_fenaban": round(rb_fenaban, 2),
        "adicional_fenaban": round(adicional_fenaban, 2),
        "plr_social": round(plr_social, 2),
        "total_plr_pre_teto": round(total_plr, 2),
        "total_plr_pos_teto": round(total_pos_teto, 2),
        "bruto_primeira_parcela": bruto_setembro,
        "ir_primeira_parcela": ir_setembro,
        "liquido_primeira_parcela": liquido_setembro,
        # parâmetros usados (transparência)
        "constantes_2025": {
            "fixo_fenaban": FENABAN_FIXO_2025,
            "teto_rb_fenaban": FENABAN_TETO_RB_2025,
            "teto_rb_majorada_info": FENABAN_TETO_RB_MAJORADA_2025,
            "teto_adicional_fenaban": FENABAN_ADIC_TETO_2025,
            "n_empregados": NUM_EMPREGADOS_2025,
            "lucro_liquido": LUCRO_LIQUIDO_2025,
            "inpc_info": INPC_ATE_AGO_2025,
            "cap_total_3_rbs": 3 * e.salario_base,
        }
    }

# =========================
# Utilitário de formatação
# =========================
def brl(x: float) -> str:
    s = f"{x:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")

# =========================
# CLI simples
# =========================
if __name__ == "__main__":
    print("=== PLR CAIXA 2025 — 1ª parcela (somente CAIXA) ===")
    try:
        salario = float(input("Salário base (ex.: 8000): ").strip().replace(",", "."))
        meses = int(input("Meses trabalhados em 2025 (1-12) [padrão 12]: ").strip() or "12")
        plr_marco = float(input("PLR BRUTA recebida em Mar/2025 (2ª parcela do ano anterior): ").strip().replace(",", "."))

        res = calcular_plr_caixa_primeira_parcela_2025(
            EntradaCaixa2025(salario_base=salario, meses_trabalhados=meses, plr_bruta_marco_2025=plr_marco)
        )

        print("\n--- Resultado (CAIXA 2025) ---")
        
        print("Bruto 1ª parcela (50%):     ", brl(res["bruto_primeira_parcela"]))
        print("IR 1ª parcela (compensado): ", brl(res["ir_primeira_parcela"]))
        print("Líquido 1ª parcela:         ", brl(res["liquido_primeira_parcela"]))
       

    except Exception as err:
        print("Erro:", err)
