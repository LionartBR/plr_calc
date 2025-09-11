from dataclasses import dataclass, asdict
from typing import Dict, Literal
import re
from decimal import Decimal, InvalidOperation

# =========================
# Configuração (2025)
# =========================

@dataclass(frozen=True)
class PLRConfig:
    # --- Fenaban (2025) ---
    P_fix_ano: float = 3532.93       # parcela fixa anual (2025)
    T_RB_ano: float = 18952.48       # teto da Regra Básica anual (2025)
    P_fix_adiant: float = 2119.76    # parcela fixa usada no adiantamento
    T_RB_adiant: float = 11371.47    # teto da RB no adiantamento
    T_ADD_anual: float = 7336.62     # teto individual da parcela 2,2% (2025)

    # --- Percentuais fixos do ACT (referência) ---
    pct_RB_ano: float = 0.90         # 90% do salário (anual)
    pct_RB_adiant: float = 0.45      # 45% do salário (adiantamento)
    pct_ADD: float = 0.022           # 2,2% (teórico)
    pct_SOC: float = 0.04            # 4%   (teórico)
    pct_global: float = 0.15         # teto global: 15% do lucro anual

    # --- Calibração empírica (seus dados) ---
    #   S1 (adiantamento) ~ 3,415% do lucro semestral / empregado (ciclo 2024)
    #   Anual (fechamento) ~ 6,414% do lucro anual / empregado (ciclo 2023)
    alpha_S1_eff: float = 0.03415
    beta_A_eff: float  = 0.06414


# =========================
# Utilidades BRL
# =========================

def parse_brl(txt: str) -> float:
    if txt is None:
        raise ValueError("valor vazio")
    raw = txt.strip().replace("R$", "").strip()
    raw = re.sub(r"\s+", "", raw)
    raw_no_thousand = raw.replace(".", "")
    canonical = raw_no_thousand.replace(",", ".")
    try:
        return float(Decimal(canonical))
    except (InvalidOperation, ValueError):
        raise ValueError(f"não consegui interpretar '{txt}' como número em BRL")

def format_brl(valor: float) -> str:
    inteiro, centavos = divmod(int(round(valor * 100)), 100)
    s_int = f"{inteiro:,}".replace(",", ".")
    s_cent = f"{centavos:02d}"
    return f"R$ {s_int},{s_cent}"


# =========================
# Núcleo do cálculo (calibração aplicada)
# =========================

def _validar_inputs(S: float, N: int, L_S1: float, L_A: float) -> None:
    if S <= 0:
        raise ValueError("Salário (S) deve ser > 0.")
    if N <= 0:
        raise ValueError("Número de empregados (N) deve ser > 0.")
    if L_S1 < 0 or L_A < 0:
        raise ValueError("Lucros (L_S1, L_A) devem ser >= 0.")

def calcular_plr(
    S: float,            # Remuneração Base (salário mensal)
    N: int,              # Número de empregados
    L_S1: float,         # Lucro líquido do 1º semestre
    L_A: float,          # Lucro líquido anual
    cfg: PLRConfig = PLRConfig(),
    regra_reducao_global: Literal["proporcional", "cortar_add_primeiro"] = "proporcional"
) -> Dict[str, float]:
    """
    Calcula PLR com calibração:
      - S1 usa cfg.alpha_S1_eff (percentual efetivo sobre lucro semestral / empregado)
      - Anual usa cfg.beta_A_eff (percentual efetivo sobre lucro anual / empregado)
    A linear é dividida entre "2,2%" e "4%" na proporção teórica (2,2 : 4) para exibição.
    """
    _validar_inputs(S, N, L_S1, L_A)

    # Proporção para dividir a linear entre "2,2%" e "4%"
    peso_add = cfg.pct_ADD / (cfg.pct_ADD + cfg.pct_SOC)  # ~0.3548387
    peso_soc = 1.0 - peso_add

    # --- Regra Básica Fenaban ---
    RB_ano_bruta = cfg.pct_RB_ano * S + cfg.P_fix_ano
    RB_ano = min(RB_ano_bruta, cfg.T_RB_ano)

    RB_S1_bruta = cfg.pct_RB_adiant * S + cfg.P_fix_adiant
    RB_S1 = min(RB_S1_bruta, cfg.T_RB_adiant)

    # --- Parcelas lineares (calibradas) ---
    percap_S1 = L_S1 / N
    percap_A  = L_A / N

    linear_S1_cal = cfg.alpha_S1_eff * percap_S1     # S1
    linear_A_cal  = cfg.beta_A_eff  * percap_A       # Anual

    # Dividir linear calibrada nas “etiquetas” 2,2% e 4%
    ADD_S1 = linear_S1_cal * peso_add
    SOC_S1 = linear_S1_cal * peso_soc

    # Teóricos (só referência/diagnóstico)
    ADD_A_teor = cfg.pct_ADD * percap_A
    SOC_A_teor = cfg.pct_SOC * percap_A

    ADD_A_pre = linear_A_cal * peso_add
    ADD_A = min(ADD_A_pre, cfg.T_ADD_anual)          # teto individual 2,2%
    SOC_A = linear_A_cal * peso_soc                  # Social calibrada (sem garantia explícita)

    # --- Totais e teto global (15%) ---
    PLR_A_bruta = RB_ano + ADD_A + SOC_A
    T_global = cfg.pct_global * L_A / N

    if PLR_A_bruta <= T_global + 1e-9:
        ADD_A_cap = ADD_A
        SOC_A_cap = SOC_A
        PLR_A = PLR_A_bruta
        reducao_global = 0.0
    else:
        target_linear = max(0.0, T_global - RB_ano)

        if regra_reducao_global == "proporcional":
            base_add = max(ADD_A, 0.0)
            base_soc = max(SOC_A, 0.0)
            base_total = base_add + base_soc
            if base_total <= 1e-9:
                ADD_A_cap = 0.0
                SOC_A_cap = 0.0
            else:
                fator = max(0.0, min(1.0, target_linear / base_total))
                ADD_A_cap = base_add * fator
                SOC_A_cap = base_soc * fator

        elif regra_reducao_global == "cortar_add_primeiro":
            ADD_A_cap = max(0.0, min(ADD_A, target_linear))
            SOC_A_cap = max(0.0, min(SOC_A, target_linear - ADD_A_cap))
        else:
            raise ValueError("regra_reducao_global inválida")

        PLR_A_uncapped = RB_ano + ADD_A_cap + SOC_A_cap
        PLR_A = min(PLR_A_uncapped, T_global)
        reducao_global = PLR_A_bruta - PLR_A

    # --- Adiantamento e fechamento ---
    PLR_S1 = RB_S1 + ADD_S1 + SOC_S1

    delta_ADD = max(0.0, ADD_A_cap - ADD_S1)
    delta_SOC = max(0.0, SOC_A_cap - SOC_S1)
    delta_RB = max(0.0, RB_ano - RB_S1)

    fechamento_prev = delta_RB + delta_ADD + delta_SOC
    fechamento = max(0.0, min(fechamento_prev, max(0.0, PLR_A - PLR_S1)))

    # --- Saída detalhada (mantém chaves usadas no app) ---
    return {
        # Inputs
        "S": float(S), "N": int(N), "L_S1": float(L_S1), "L_A": float(L_A),

        # Config
        **{f"cfg_{k}": v for k, v in asdict(cfg).items()},
        "T_global": T_global,

        # RB
        "RB_ano_bruta": RB_ano_bruta, "RB_ano": RB_ano,
        "RB_S1_bruta": RB_S1_bruta, "RB_S1": RB_S1,

        # 2,2%
        "ADD_A_teor": ADD_A_teor, "ADD_A_cap": ADD_A_cap, "ADD_S1": ADD_S1,

        # 4% Social
        "SOC_A_teor": SOC_A_teor, "SOC_A_cap": SOC_A_cap, "SOC_S1": SOC_S1,

        # Totais
        "PLR_A_bruta": PLR_A_bruta, "PLR_A_pos_teto_global": PLR_A,
        "reducao_global_aplicada": reducao_global,
        "PLR_S1": PLR_S1, "fechamento_prev": fechamento_prev, "fechamento": fechamento,

        # Principais
        "adiantamento": PLR_S1, "total_anual": PLR_A, "segunda_parcela": fechamento
    }
