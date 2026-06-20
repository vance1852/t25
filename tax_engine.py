from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import json

MONTHLY_TAX_BRACKETS = [
    (3000, 0.03, 0),
    (12000, 0.10, 210),
    (25000, 0.20, 1410),
    (35000, 0.25, 2660),
    (55000, 0.30, 4410),
    (80000, 0.35, 7160),
    (float('inf'), 0.45, 15160),
]

ANNUAL_TAX_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float('inf'), 0.45, 181920),
]

BASIC_EXEMPTION = 5000

SPECIAL_DEDUCTION_ITEMS = {
    "children_education": {"name": "子女教育", "default": 2000, "unit": "元/月", "desc": "每个子女2,000元/月"},
    "continuing_education": {"name": "继续教育", "default": 400, "unit": "元/月", "desc": "学历教育400元/月，职业资格3,600元/年"},
    "housing_loan": {"name": "住房贷款利息", "default": 1000, "unit": "元/月", "desc": "首套房贷1,000元/月"},
    "housing_rent": {"name": "住房租金", "default": 1500, "unit": "元/月", "desc": "直辖市/省会1,500元，市辖区户籍>100万1,100元，其他800元"},
    "elderly_support": {"name": "赡养老人", "default": 3000, "unit": "元/月", "desc": "独生子女3,000元/月，非独生子女分摊"},
    "infant_care": {"name": "3岁以下婴幼儿照护", "default": 2000, "unit": "元/月", "desc": "每个婴幼儿2,000元/月"},
    "medical_expense": {"name": "大病医疗", "default": 0, "unit": "元/年", "desc": "个人负担超15,000元部分，最高80,000元/年"},
}

DEFAULT_SI_RATES = {
    "pension": {"name": "养老保险", "rate": 0.08, "desc": "个人8%"},
    "medical": {"name": "医疗保险", "rate": 0.02, "desc": "个人2%"},
    "unemployment": {"name": "失业保险", "rate": 0.005, "desc": "个人0.5%"},
    "housing_fund": {"name": "住房公积金", "rate": 0.12, "desc": "个人5%-12%，默认12%"},
}


@dataclass
class MonthlyInput:
    salary: float = 0.0
    si_total: float = 0.0
    si_base: float = 0.0
    si_rates: Dict[str, float] = field(default_factory=lambda: {
        "pension": 0.08, "medical": 0.02, "unemployment": 0.005, "housing_fund": 0.12
    })
    si_use_rates: bool = False
    special_deductions: Dict[str, float] = field(default_factory=lambda: {
        k: 0.0 for k in SPECIAL_DEDUCTION_ITEMS
    })

    @property
    def si_deduction(self) -> float:
        if self.si_use_rates and self.si_base > 0:
            return self.si_base * sum(self.si_rates.values())
        return self.si_total

    @property
    def monthly_special_deduction(self) -> float:
        total = 0.0
        for k, v in self.special_deductions.items():
            if k == "medical_expense":
                continue
            total += v
        return total

    @property
    def annual_medical_deduction(self) -> float:
        return self.special_deductions.get("medical_expense", 0.0)


@dataclass
class MonthlyResult:
    month: int
    salary: float
    si_deduction: float
    special_deduction: float
    cumulative_income: float
    cumulative_deduction: float
    cumulative_taxable: float
    tax_rate: float
    quick_deduction: float
    cumulative_tax: float
    monthly_tax: float
    take_home: float


@dataclass
class AnnualResult:
    months: List[MonthlyResult]
    total_salary: float
    total_si: float
    total_special: float
    total_taxable: float
    total_tax: float
    total_take_home: float
    effective_rate: float
    annual_medical: float


def _find_bracket(taxable_income: float, brackets: list) -> Tuple[float, float]:
    for upper, rate, qd in brackets:
        if taxable_income <= upper:
            return rate, qd
    return brackets[-1][1], brackets[-1][2]


def calc_annual(monthly_inputs: List[MonthlyInput]) -> AnnualResult:
    results = []
    cum_income = 0.0
    cum_si = 0.0
    cum_special = 0.0
    cum_tax = 0.0
    annual_medical = 0.0

    for i, mi in enumerate(monthly_inputs):
        month = i + 1
        cum_income += mi.salary
        cum_si += mi.si_deduction
        cum_special += mi.monthly_special_deduction
        cum_special_actual = cum_special

        if month == 12:
            annual_medical = mi.annual_medical_deduction
            cum_special_actual += annual_medical
        else:
            annual_medical = 0.0

        cum_deduction = cum_si + cum_special_actual + BASIC_EXEMPTION * month
        cum_taxable = cum_income - cum_deduction
        if cum_taxable < 0:
            cum_taxable = 0.0

        rate, qd = _find_bracket(cum_taxable, ANNUAL_TAX_BRACKETS)
        cum_tax_calc = cum_taxable * rate - qd
        if cum_tax_calc < 0:
            cum_tax_calc = 0.0

        monthly_tax = cum_tax_calc - cum_tax
        if monthly_tax < 0:
            monthly_tax = 0.0

        take_home = mi.salary - mi.si_deduction - monthly_tax

        results.append(MonthlyResult(
            month=month,
            salary=mi.salary,
            si_deduction=mi.si_deduction,
            special_deduction=mi.monthly_special_deduction,
            cumulative_income=cum_income,
            cumulative_deduction=cum_deduction,
            cumulative_taxable=cum_taxable,
            tax_rate=rate,
            quick_deduction=qd,
            cumulative_tax=cum_tax_calc,
            monthly_tax=monthly_tax,
            take_home=take_home,
        ))
        cum_tax = cum_tax_calc

    total_salary = sum(r.salary for r in results)
    total_si = sum(r.si_deduction for r in results)
    total_special = sum(r.special_deduction for r in results)
    total_tax = results[-1].cumulative_tax if results else 0
    total_take_home = sum(r.take_home for r in results)
    total_taxable = results[-1].cumulative_taxable if results else 0
    effective_rate = total_tax / total_salary * 100 if total_salary > 0 else 0

    return AnnualResult(
        months=results,
        total_salary=total_salary,
        total_si=total_si,
        total_special=total_special,
        total_taxable=total_taxable,
        total_tax=total_tax,
        total_take_home=total_take_home,
        effective_rate=effective_rate,
        annual_medical=annual_medical,
    )


def calc_bonus_separate(bonus: float) -> Tuple[float, float, float]:
    if bonus <= 0:
        return 0.0, 0.0, 0.0
    monthly_avg = bonus / 12
    rate, qd = _find_bracket(monthly_avg, MONTHLY_TAX_BRACKETS)
    tax = bonus * rate - qd
    if tax < 0:
        tax = 0.0
    after_tax = bonus - tax
    return tax, after_tax, rate


def calc_bonus_combined(bonus: float, annual_taxable_income: float) -> Tuple[float, float, float]:
    if bonus <= 0:
        return 0.0, 0.0, 0.0
    combined_taxable = annual_taxable_income + bonus
    rate, qd = _find_bracket(combined_taxable, ANNUAL_TAX_BRACKETS)
    combined_tax = combined_taxable * rate - qd

    rate_orig, qd_orig = _find_bracket(annual_taxable_income, ANNUAL_TAX_BRACKETS)
    original_tax = annual_taxable_income * rate_orig - qd_orig
    if original_tax < 0:
        original_tax = 0.0

    bonus_tax = combined_tax - original_tax
    if bonus_tax < 0:
        bonus_tax = 0.0
    after_tax = bonus - bonus_tax
    return bonus_tax, after_tax, rate


@dataclass
class CriticalPoint:
    boundary: float
    tax_at_boundary: float
    after_tax_at_boundary: float
    blind_spot_upper: float
    after_tax_at_blind_upper: float
    lower_rate: float
    higher_rate: float
    loss_at_boundary: float


def find_bonus_critical_points() -> List[CriticalPoint]:
    points = []
    for i in range(len(MONTHLY_TAX_BRACKETS) - 1):
        upper = MONTHLY_TAX_BRACKETS[i][0]
        lower_rate = MONTHLY_TAX_BRACKETS[i][1]
        lower_qd = MONTHLY_TAX_BRACKETS[i][2]
        higher_rate = MONTHLY_TAX_BRACKETS[i + 1][1]
        higher_qd = MONTHLY_TAX_BRACKETS[i + 1][2]

        boundary = upper * 12

        tax_at_boundary = boundary * lower_rate - lower_qd
        after_tax_at_boundary = boundary - tax_at_boundary

        tax_just_above = (boundary + 1) * higher_rate - higher_qd
        after_tax_just_above = (boundary + 1) - tax_just_above
        loss = after_tax_at_boundary - after_tax_just_above

        blind_upper = (after_tax_at_boundary - higher_qd) / (1 - higher_rate)
        if blind_upper <= boundary:
            blind_upper = boundary

        tax_at_blind = blind_upper * higher_rate - higher_qd
        after_tax_blind = blind_upper - tax_at_blind

        points.append(CriticalPoint(
            boundary=boundary,
            tax_at_boundary=tax_at_boundary,
            after_tax_at_boundary=after_tax_at_boundary,
            blind_spot_upper=round(blind_upper, 2),
            after_tax_at_blind_upper=round(after_tax_blind, 2),
            lower_rate=lower_rate,
            higher_rate=higher_rate,
            loss_at_boundary=round(loss, 2),
        ))
    return points


def check_bonus_trap(bonus: float, critical_points: List[CriticalPoint]) -> Optional[str]:
    for cp in critical_points:
        if cp.boundary < bonus <= cp.blind_spot_upper:
            return (
                f"⚠ 年终奖 {bonus:,.2f} 元落在无效区间 "
                f"({cp.boundary:,.0f} ~ {cp.blind_spot_upper:,.2f})！\n"
                f"多发 {bonus - cp.boundary:,.2f} 元，到手反而少 "
                f"{cp.after_tax_at_boundary - (bonus - calc_bonus_separate(bonus)[0]):,.2f} 元。\n"
                f"建议：将年终奖降至 {cp.boundary:,.0f} 元，或超过 {cp.blind_spot_upper:,.2f} 元。"
            )
    return None


@dataclass
class BonusComparison:
    bonus: float
    separate_tax: float
    separate_after_tax: float
    separate_rate: float
    combined_tax: float
    combined_after_tax: float
    combined_rate: float
    better_method: str
    tax_diff: float
    trap_warning: Optional[str]


def compare_bonus_methods(bonus: float, annual_taxable_income: float) -> BonusComparison:
    sep_tax, sep_after, sep_rate = calc_bonus_separate(bonus)
    com_tax, com_after, com_rate = calc_bonus_combined(bonus, annual_taxable_income)

    critical_points = find_bonus_critical_points()
    trap = check_bonus_trap(bonus, critical_points)

    if sep_tax <= com_tax:
        better = "单独计税"
        diff = com_tax - sep_tax
    else:
        better = "并入综合所得"
        diff = sep_tax - com_tax

    return BonusComparison(
        bonus=bonus,
        separate_tax=round(sep_tax, 2),
        separate_after_tax=round(sep_after, 2),
        separate_rate=sep_rate,
        combined_tax=round(com_tax, 2),
        combined_after_tax=round(com_after, 2),
        combined_rate=com_rate,
        better_method=better,
        tax_diff=round(diff, 2),
        trap_warning=trap,
    )


@dataclass
class ScenarioResult:
    name: str
    annual_result: AnnualResult
    bonus_comparison: Optional[BonusComparison] = None
    total_tax_with_bonus: float = 0.0
    total_take_home_with_bonus: float = 0.0
    total_compensation: float = 0.0
    effective_rate_with_bonus: float = 0.0


def run_scenario(
    name: str,
    monthly_inputs: List[MonthlyInput],
    bonus: float = 0.0,
    bonus_method: str = "auto",
) -> ScenarioResult:
    annual = calc_annual(monthly_inputs)
    annual_taxable = annual.total_taxable

    bc = None
    bonus_tax = 0.0
    bonus_after = 0.0
    if bonus > 0:
        bc = compare_bonus_methods(bonus, annual_taxable)
        if bonus_method == "separate":
            bonus_tax = bc.separate_tax
            bonus_after = bc.separate_after_tax
        elif bonus_method == "combined":
            bonus_tax = bc.combined_tax
            bonus_after = bc.combined_after_tax
        else:
            if bc.better_method == "单独计税":
                bonus_tax = bc.separate_tax
                bonus_after = bc.separate_after_tax
            else:
                bonus_tax = bc.combined_tax
                bonus_after = bc.combined_after_tax

    total_tax = annual.total_tax + bonus_tax
    total_take = annual.total_take_home + bonus_after
    total_comp = annual.total_salary + bonus
    eff_rate = total_tax / total_comp * 100 if total_comp > 0 else 0

    return ScenarioResult(
        name=name,
        annual_result=annual,
        bonus_comparison=bc,
        total_tax_with_bonus=round(total_tax, 2),
        total_take_home_with_bonus=round(total_take, 2),
        total_compensation=round(total_comp, 2),
        effective_rate_with_bonus=round(eff_rate, 2),
    )


@dataclass
class OptimizationSplit:
    salary_annual: float
    bonus_annual: float
    salary_tax: float
    bonus_tax: float
    total_tax: float
    total_take_home: float
    effective_rate: float


def optimize_income_split(
    total_annual: float,
    si_monthly: float = 0.0,
    special_monthly: float = 0.0,
    step: float = 1000,
) -> List[OptimizationSplit]:
    results = []
    bonus_candidates = [0.0]

    for upper, rate, qd in MONTHLY_TAX_BRACKETS:
        if upper * 12 <= total_annual:
            bonus_candidates.append(upper * 12)

    critical_points = find_bonus_critical_points()
    cp_boundaries = set()
    for cp in critical_points:
        cp_boundaries.add(cp.boundary)
        cp_boundaries.add(cp.blind_spot_upper)

    for b in cp_boundaries:
        if 0 < b <= total_annual:
            bonus_candidates.append(b)

    bonus_candidates = sorted(set(bonus_candidates))
    valid = []
    for b in bonus_candidates:
        if b <= total_annual:
            valid.append(b)
    bonus_candidates = valid

    for bonus in bonus_candidates:
        salary_annual = total_annual - bonus

        monthly_salary = salary_annual / 12 if salary_annual > 0 else 0
        inputs = []
        for _ in range(12):
            inputs.append(MonthlyInput(
                salary=monthly_salary,
                si_total=si_monthly,
                special_deductions={k: special_monthly / 6 if k != "medical_expense" else 0.0
                                    for k in SPECIAL_DEDUCTION_ITEMS},
            ))
        annual_result = calc_annual(inputs)

        if bonus > 0:
            sep_tax, sep_after, _ = calc_bonus_separate(bonus)
            com_tax, com_after, _ = calc_bonus_combined(bonus, annual_result.total_taxable)
            if sep_tax <= com_tax:
                bonus_tax = sep_tax
                bonus_after = sep_after
            else:
                bonus_tax = com_tax
                bonus_after = com_after
        else:
            bonus_tax = 0.0
            bonus_after = 0.0

        total_tax = annual_result.total_tax + bonus_tax
        total_take = annual_result.total_take_home + bonus_after
        eff = total_tax / total_annual * 100 if total_annual > 0 else 0

        results.append(OptimizationSplit(
            salary_annual=round(salary_annual, 2),
            bonus_annual=round(bonus, 2),
            salary_tax=round(annual_result.total_tax, 2),
            bonus_tax=round(bonus_tax, 2),
            total_tax=round(total_tax, 2),
            total_take_home=round(total_take, 2),
            effective_rate=round(eff, 2),
        ))

    results.sort(key=lambda x: x.total_tax)
    return results


def generate_bonus_tax_curve(
    annual_taxable_income: float,
    max_bonus: float = 500000,
    step: float = 500,
) -> Dict[str, List[float]]:
    bonuses = []
    separate_taxes = []
    combined_taxes = []

    b = 0
    while b <= max_bonus:
        bonuses.append(b)
        st, _, _ = calc_bonus_separate(b)
        ct, _, _ = calc_bonus_combined(b, annual_taxable_income)
        separate_taxes.append(st)
        combined_taxes.append(ct)
        b += step

    return {
        "bonus": bonuses,
        "separate_tax": separate_taxes,
        "combined_tax": combined_taxes,
    }


def scenario_to_dict(scenario: ScenarioResult) -> dict:
    d = {
        "name": scenario.name,
        "total_tax_with_bonus": scenario.total_tax_with_bonus,
        "total_take_home_with_bonus": scenario.total_take_home_with_bonus,
        "effective_rate_with_bonus": scenario.effective_rate_with_bonus,
    }
    return d


def export_report(scenarios: List[ScenarioResult], critical_points: List[CriticalPoint]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("个人所得税测算报告")
    lines.append("=" * 70)

    for s in scenarios:
        lines.append("")
        lines.append(f"【方案：{s.name}】")
        ar = s.annual_result
        lines.append(f"  年度工资总额：{ar.total_salary:,.2f} 元")
        lines.append(f"  年度五险一金：{ar.total_si:,.2f} 元")
        lines.append(f"  年度专项扣除：{ar.total_special:,.2f} 元")
        lines.append(f"  全年应纳税所得额：{ar.total_taxable:,.2f} 元")
        lines.append(f"  全年工资纳税：{ar.total_tax:,.2f} 元")
        lines.append(f"  全年工资到手：{ar.total_take_home:,.2f} 元")
        lines.append(f"  工资实际税负率：{ar.effective_rate:.2f}%")
        lines.append("")

        lines.append("  月份  月薪        五险一金    累计应税额  当月税率  当月预扣税  当月到手")
        lines.append("  " + "-" * 74)
        for m in ar.months:
            lines.append(
                f"  {m.month:>2}月  {m.salary:>10,.2f}  {m.si_deduction:>8,.2f}  "
                f"{m.cumulative_taxable:>10,.2f}  {m.tax_rate * 100:>6.1f}%  "
                f"{m.monthly_tax:>10,.2f}  {m.take_home:>10,.2f}"
            )

        if s.bonus_comparison:
            bc = s.bonus_comparison
            lines.append("")
            lines.append(f"  年终奖金额：{bc.bonus:,.2f} 元")
            lines.append(f"  单独计税：纳税 {bc.separate_tax:,.2f} 元，到手 {bc.separate_after_tax:,.2f} 元")
            lines.append(f"  并入综合：纳税 {bc.combined_tax:,.2f} 元，到手 {bc.combined_after_tax:,.2f} 元")
            lines.append(f"  推荐方式：{bc.better_method}（节省 {bc.tax_diff:,.2f} 元）")
            if bc.trap_warning:
                lines.append(f"  {bc.trap_warning}")

        lines.append("")
        lines.append(f"  含年终奖总纳税：{s.total_tax_with_bonus:,.2f} 元")
        lines.append(f"  含年终奖总到手：{s.total_take_home_with_bonus:,.2f} 元")
        lines.append(f"  综合实际税负率：{s.effective_rate_with_bonus:.2f}%")

    lines.append("")
    lines.append("=" * 70)
    lines.append("年终奖临界陷阱参考表")
    lines.append("=" * 70)
    for cp in critical_points:
        lines.append(
            f"  临界点 {cp.boundary:>10,.0f} 元 → 无效区间上限 {cp.blind_spot_upper:>12,.2f} 元  "
            f"（{cp.lower_rate * 100:.0f}% → {cp.higher_rate * 100:.0f}%，跨档损失 {cp.loss_at_boundary:,.2f} 元）"
        )

    return "\n".join(lines)
