import sys
import os
import json
from typing import List, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QFileDialog, QMessageBox, QTextEdit, QScrollArea,
    QFormLayout, QSizePolicy, QStatusBar, QAction, QMenuBar,
)
from PyQt5.QtCore import Qt, QLocale
from PyQt5.QtGui import QColor, QFont, QDoubleValidator

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from tax_engine import (
    MonthlyInput, AnnualResult, MonthlyResult, calc_annual,
    calc_bonus_separate, calc_bonus_combined, compare_bonus_methods,
    find_bonus_critical_points, check_bonus_trap, run_scenario,
    optimize_income_split, generate_bonus_tax_curve, export_report,
    CriticalPoint, ScenarioResult, OptimizationSplit,
    SPECIAL_DEDUCTION_ITEMS, DEFAULT_SI_RATES, ANNUAL_TAX_BRACKETS,
    MONTHLY_TAX_BRACKETS, BASIC_EXEMPTION,
)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=8, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


class MonthlyCalcTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._monthly_cache = [MonthlyInput() for _ in range(12)]
        self._init_ui()

    def _init_ui(self):
        main_split = QSplitter(Qt.Horizontal)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        salary_group = QGroupBox("月度工资")
        sl = QVBoxLayout(salary_group)
        hl = QHBoxLayout()
        hl.addWidget(QLabel("基本月薪："))
        self.base_salary_spin = QDoubleSpinBox()
        self.base_salary_spin.setRange(0, 9999999)
        self.base_salary_spin.setDecimals(2)
        self.base_salary_spin.setSuffix(" 元")
        self.base_salary_spin.setValue(15000)
        self.base_salary_spin.setSingleStep(500)
        hl.addWidget(self.base_salary_spin)
        self.apply_all_btn = QPushButton("应用到全部月份")
        self.apply_all_btn.clicked.connect(self._apply_salary_all)
        hl.addWidget(self.apply_all_btn)
        sl.addLayout(hl)

        month_label = QLabel("各月工资（支持不同，0=使用基本月薪）：")
        sl.addWidget(month_label)
        self.monthly_salary_spins = []
        grid = QHBoxLayout()
        for i in range(12):
            col = QVBoxLayout()
            lbl = QLabel(f"{i+1}月")
            lbl.setAlignment(Qt.AlignCenter)
            col.addWidget(lbl)
            spin = QDoubleSpinBox()
            spin.setRange(0, 9999999)
            spin.setDecimals(2)
            spin.setSuffix(" 元")
            spin.setValue(0)
            spin.setSpecialValueText("默认")
            col.addWidget(spin)
            self.monthly_salary_spins.append(spin)
            grid.addLayout(col)
        sl.addLayout(grid)
        left_layout.addWidget(salary_group)

        si_group = QGroupBox("五险一金")
        si_l = QVBoxLayout(si_group)
        self.si_mode_combo = QComboBox()
        self.si_mode_combo.addItems(["直接填写总额", "按基数和比例计算"])
        self.si_mode_combo.currentIndexChanged.connect(self._toggle_si_mode)
        si_l.addWidget(self.si_mode_combo)

        self.si_total_spin = QDoubleSpinBox()
        self.si_total_spin.setRange(0, 9999999)
        self.si_total_spin.setDecimals(2)
        self.si_total_spin.setSuffix(" 元/月")
        self.si_total_spin.setValue(2500)
        si_l.addWidget(QLabel("每月五险一金总额："))
        si_l.addWidget(self.si_total_spin)

        self.si_base_spin = QDoubleSpinBox()
        self.si_base_spin.setRange(0, 9999999)
        self.si_base_spin.setDecimals(2)
        self.si_base_spin.setSuffix(" 元")
        self.si_base_spin.setValue(15000)
        self.si_base_spin.setEnabled(False)
        si_l.addWidget(QLabel("缴费基数："))
        si_l.addWidget(self.si_base_spin)

        self.si_rate_spins = {}
        for key, info in DEFAULT_SI_RATES.items():
            hl2 = QHBoxLayout()
            hl2.addWidget(QLabel(f"{info['name']}（{info['desc']}）："))
            spin = QDoubleSpinBox()
            spin.setRange(0, 1)
            spin.setDecimals(4)
            spin.setValue(info['rate'])
            spin.setSingleStep(0.005)
            spin.setEnabled(False)
            self.si_rate_spins[key] = spin
            hl2.addWidget(spin)
            si_l.addLayout(hl2)

        self.si_calc_label = QLabel("")
        si_l.addWidget(self.si_calc_label)
        self.si_base_spin.valueChanged.connect(self._update_si_calc)
        for s in self.si_rate_spins.values():
            s.valueChanged.connect(self._update_si_calc)

        left_layout.addWidget(si_group)

        spec_group = QGroupBox("专项附加扣除")
        spec_l = QVBoxLayout(spec_group)
        self.spec_spins = {}
        for key, info in SPECIAL_DEDUCTION_ITEMS.items():
            hl3 = QHBoxLayout()
            hl3.addWidget(QLabel(f"{info['name']}："))
            spin = QDoubleSpinBox()
            spin.setRange(0, 999999)
            spin.setDecimals(2)
            spin.setSuffix(f" {info['unit']}")
            spin.setValue(0)
            spin.setSpecialValueText("0")
            spin.setToolTip(info['desc'])
            self.spec_spins[key] = spin
            hl3.addWidget(spin)
            tip_label = QLabel(info['desc'])
            tip_label.setStyleSheet("color: gray; font-size: 10px;")
            hl3.addWidget(tip_label)
            spec_l.addLayout(hl3)

        left_layout.addWidget(spec_group)
        left_layout.addStretch()
        left_scroll.setWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.calc_btn = QPushButton("计  算")
        self.calc_btn.setStyleSheet(
            "QPushButton{background:#1890ff;color:white;font-size:16px;"
            "padding:8px;border-radius:4px;font-weight:bold}"
            "QPushButton:hover{background:#40a9ff}"
        )
        self.calc_btn.clicked.connect(self._do_calc)
        right_layout.addWidget(self.calc_btn)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            "font-size:14px; font-weight:bold; padding:8px; "
            "background:#f0f5ff; border-radius:4px;"
        )
        right_layout.addWidget(self.summary_label)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(8)
        self.result_table.setHorizontalHeaderLabels([
            "月份", "月薪", "五险一金", "累计应纳税所得额",
            "适用税率", "当月预扣税", "累计预扣税", "到手工资"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setMinimumHeight(300)
        right_layout.addWidget(self.result_table)

        self.canvas = MplCanvas(self, width=10, height=5)
        right_layout.addWidget(self.canvas)

        main_split.addWidget(left_scroll)
        main_split.addWidget(right_widget)
        main_split.setStretchFactor(0, 2)
        main_split.setStretchFactor(1, 3)

        outer = QVBoxLayout(self)
        outer.addWidget(main_split)

    def _toggle_si_mode(self, idx):
        use_rates = idx == 1
        self.si_total_spin.setEnabled(not use_rates)
        self.si_base_spin.setEnabled(use_rates)
        for s in self.si_rate_spins.values():
            s.setEnabled(use_rates)
        if use_rates:
            self._update_si_calc()

    def _update_si_calc(self):
        base = self.si_base_spin.value()
        total_rate = sum(s.value() for s in self.si_rate_spins.values())
        calc = base * total_rate
        self.si_calc_label.setText(f"计算结果：{calc:,.2f} 元/月")

    def _apply_salary_all(self):
        for spin in self.monthly_salary_spins:
            spin.setValue(0)

    def _get_monthly_inputs(self) -> List[MonthlyInput]:
        inputs = []
        base_salary = self.base_salary_spin.value()
        use_rates = self.si_mode_combo.currentIndex() == 1

        for i in range(12):
            salary = self.monthly_salary_spins[i].value()
            if salary <= 0:
                salary = base_salary

            if use_rates:
                si_base = self.si_base_spin.value()
                rates = {k: s.value() for k, s in self.si_rate_spins.items()}
                mi = MonthlyInput(
                    salary=salary, si_total=0, si_base=si_base,
                    si_rates=rates, si_use_rates=True,
                    special_deductions={k: s.value() for k, s in self.spec_spins.items()},
                )
            else:
                mi = MonthlyInput(
                    salary=salary, si_total=self.si_total_spin.value(),
                    special_deductions={k: s.value() for k, s in self.spec_spins.items()},
                )
            inputs.append(mi)
        return inputs

    def _do_calc(self):
        inputs = self._get_monthly_inputs()
        self._monthly_cache = inputs
        result = calc_annual(inputs)
        self._fill_table(result)
        self._draw_charts(result)
        self._fill_summary(result)

    def _fill_table(self, result: AnnualResult):
        self.result_table.setRowCount(12)
        for i, m in enumerate(result.months):
            items = [
                f"{m.month}月",
                f"{m.salary:,.2f}",
                f"{m.si_deduction:,.2f}",
                f"{m.cumulative_taxable:,.2f}",
                f"{m.tax_rate * 100:.1f}%",
                f"{m.monthly_tax:,.2f}",
                f"{m.cumulative_tax:,.2f}",
                f"{m.take_home:,.2f}",
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 4 and m.tax_rate > 0.03:
                    item.setForeground(QColor(220, 50, 50))
                if j == 5:
                    if m.monthly_tax > 0 and i > 0 and result.months[i-1].monthly_tax > 0:
                        if m.monthly_tax > result.months[i-1].monthly_tax * 1.2:
                            item.setForeground(QColor(220, 50, 50))
                self.result_table.setItem(i, j, item)

    def _fill_summary(self, result: AnnualResult):
        self.summary_label.setText(
            f"全年工资 {result.total_salary:,.2f} 元 | "
            f"全年纳税 {result.total_tax:,.2f} 元 | "
            f"全年到手 {result.total_take_home:,.2f} 元 | "
            f"实际税负率 {result.effective_rate:.2f}%"
        )

    def _draw_charts(self, result: AnnualResult):
        self.canvas.fig.clear()

        ax1 = self.canvas.fig.add_subplot(121)
        months = [m.month for m in result.months]
        take_homes = [m.take_home for m in result.months]
        taxes = [m.monthly_tax for m in result.months]

        bar_width = 0.35
        bars1 = ax1.bar([x - bar_width/2 for x in months], take_homes, bar_width, label='到手工资', color='#52c41a', alpha=0.8)
        bars2 = ax1.bar([x + bar_width/2 for x in months], taxes, bar_width, label='预扣个税', color='#ff4d4f', alpha=0.8)
        ax1.set_xlabel('月份')
        ax1.set_ylabel('金额（元）')
        ax1.set_title('每月到手工资与预扣个税')
        ax1.legend()
        ax1.set_xticks(months)
        ax1.grid(axis='y', alpha=0.3)

        ax2 = self.canvas.fig.add_subplot(122)
        cum_taxes = [m.cumulative_tax for m in result.months]
        cum_taxables = [m.cumulative_taxable for m in result.months]
        ax2.plot(months, cum_taxables, 'o-', label='累计应纳税所得额', color='#fa8c16')
        ax2.plot(months, cum_taxes, 's-', label='累计预扣税额', color='#1890ff')

        for ub, rate, qd in ANNUAL_TAX_BRACKETS:
            if ub < cum_taxables[-1] * 1.1 and ub > 0 and ub != float('inf'):
                ax2.axhline(y=ub, color='red', linestyle='--', alpha=0.3, linewidth=0.8)
                ax2.text(12.3, ub, f'{rate*100:.0f}%档', fontsize=7, color='red', alpha=0.6)

        ax2.set_xlabel('月份')
        ax2.set_ylabel('金额（元）')
        ax2.set_title('累计应纳税所得额与累计预扣税额')
        ax2.legend()
        ax2.set_xticks(months)
        ax2.grid(axis='y', alpha=0.3)

        self.canvas.fig.tight_layout()
        self.canvas.draw()

    def get_monthly_inputs(self) -> List[MonthlyInput]:
        return self._get_monthly_inputs()

    def get_state(self) -> dict:
        return {
            "base_salary": self.base_salary_spin.value(),
            "monthly_salaries": [s.value() for s in self.monthly_salary_spins],
            "si_mode": self.si_mode_combo.currentIndex(),
            "si_total": self.si_total_spin.value(),
            "si_base": self.si_base_spin.value(),
            "si_rates": {k: s.value() for k, s in self.si_rate_spins.items()},
            "special_deductions": {k: s.value() for k, s in self.spec_spins.items()},
        }

    def set_state(self, state: dict):
        self.base_salary_spin.setValue(state.get("base_salary", 15000))
        for i, v in enumerate(state.get("monthly_salaries", [0]*12)):
            self.monthly_salary_spins[i].setValue(v)
        self.si_mode_combo.setCurrentIndex(state.get("si_mode", 0))
        self.si_total_spin.setValue(state.get("si_total", 2500))
        self.si_base_spin.setValue(state.get("si_base", 15000))
        for k, v in state.get("si_rates", {}).items():
            if k in self.si_rate_spins:
                self.si_rate_spins[k].setValue(v)
        for k, v in state.get("special_deductions", {}).items():
            if k in self.spec_spins:
                self.spec_spins[k].setValue(v)


class BonusPlanTab(QWidget):
    def __init__(self, monthly_tab: MonthlyCalcTab, parent=None):
        super().__init__(parent)
        self.monthly_tab = monthly_tab
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        top_split = QSplitter(Qt.Horizontal)

        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)

        bonus_group = QGroupBox("年终奖输入")
        bl = QVBoxLayout(bonus_group)
        hl = QHBoxLayout()
        hl.addWidget(QLabel("年终奖金额："))
        self.bonus_spin = QDoubleSpinBox()
        self.bonus_spin.setRange(0, 99999999)
        self.bonus_spin.setDecimals(2)
        self.bonus_spin.setSuffix(" 元")
        self.bonus_spin.setValue(50000)
        self.bonus_spin.setSingleStep(1000)
        hl.addWidget(self.bonus_spin)
        bl.addLayout(hl)

        self.calc_btn = QPushButton("计算对比")
        self.calc_btn.setStyleSheet(
            "QPushButton{background:#1890ff;color:white;font-size:14px;"
            "padding:6px;border-radius:4px;font-weight:bold}"
            "QPushButton:hover{background:#40a9ff}"
        )
        self.calc_btn.clicked.connect(self._do_calc)
        bl.addWidget(self.calc_btn)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(200)
        bl.addWidget(self.result_text)
        input_layout.addWidget(bonus_group)

        cp_group = QGroupBox("年终奖临界陷阱参考")
        cp_l = QVBoxLayout(cp_group)
        self.cp_table = QTableWidget()
        self.cp_table.setColumnCount(5)
        self.cp_table.setHorizontalHeaderLabels([
            "临界点（元）", "无效区间上限（元）", "低档税率", "高档税率", "跨档损失（元）"
        ])
        self.cp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cp_table.setAlternatingRowColors(True)
        cp_l.addWidget(self.cp_table)
        self._fill_critical_points()
        input_layout.addWidget(cp_group)

        top_split.addWidget(input_widget)

        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        self.canvas = MplCanvas(chart_widget, width=10, height=6)
        chart_layout.addWidget(self.canvas)
        top_split.addWidget(chart_widget)
        top_split.setStretchFactor(0, 2)
        top_split.setStretchFactor(1, 3)

        layout.addWidget(top_split)

    def _fill_critical_points(self):
        cps = find_bonus_critical_points()
        self.cp_table.setRowCount(len(cps))
        for i, cp in enumerate(cps):
            items = [
                f"{cp.boundary:,.0f}",
                f"{cp.blind_spot_upper:,.2f}",
                f"{cp.lower_rate * 100:.0f}%",
                f"{cp.higher_rate * 100:.0f}%",
                f"{cp.loss_at_boundary:,.2f}",
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 4:
                    item.setForeground(QColor(220, 50, 50))
                self.cp_table.setItem(i, j, item)

    def _do_calc(self):
        inputs = self.monthly_tab.get_monthly_inputs()
        annual_result = calc_annual(inputs)
        annual_taxable = annual_result.total_taxable
        bonus = self.bonus_spin.value()

        comparison = compare_bonus_methods(bonus, annual_taxable)

        html = f"<h3>年终奖 {bonus:,.2f} 元 计税对比</h3>"
        html += "<table border='1' cellpadding='6' style='border-collapse:collapse;'>"
        html += "<tr><th></th><th>单独计税</th><th>并入综合所得</th></tr>"
        html += f"<tr><td>应纳税额</td><td>{comparison.separate_tax:,.2f} 元</td><td>{comparison.combined_tax:,.2f} 元</td></tr>"
        html += f"<tr><td>到手金额</td><td>{comparison.separate_after_tax:,.2f} 元</td><td>{comparison.combined_after_tax:,.2f} 元</td></tr>"
        html += f"<tr><td>适用税率</td><td>{comparison.separate_rate * 100:.0f}%</td><td>{comparison.combined_rate * 100:.0f}%</td></tr>"
        html += "</table>"
        html += f"<p><b>推荐方式：{comparison.better_method}</b>（节省 {comparison.tax_diff:,.2f} 元）</p>"

        if comparison.trap_warning:
            html += f"<p style='color:red;font-weight:bold;'>{comparison.trap_warning.replace(chr(10), '<br>')}</p>"

        total_tax_sep = annual_result.total_tax + comparison.separate_tax
        total_tax_com = annual_result.total_tax + comparison.combined_tax
        total_take_sep = annual_result.total_take_home + comparison.separate_after_tax
        total_take_com = annual_result.total_take_home + comparison.combined_after_tax

        html += f"<p>全年含年终奖：<br>单独计税总纳税 {total_tax_sep:,.2f} 元，总到手 {total_take_sep:,.2f} 元<br>"
        html += f"并入综合总纳税 {total_tax_com:,.2f} 元，总到手 {total_take_com:,.2f} 元</p>"

        self.result_text.setHtml(html)
        self._draw_charts(bonus, annual_taxable, comparison)

    def _draw_charts(self, bonus: float, annual_taxable: float, comparison):
        self.canvas.fig.clear()

        ax1 = self.canvas.fig.add_subplot(121)
        methods = ['单独计税', '并入综合所得']
        taxes = [comparison.separate_tax, comparison.combined_tax]
        after = [comparison.separate_after_tax, comparison.combined_after_tax]
        x = range(len(methods))
        width = 0.3
        ax1.bar([i - width/2 for i in x], taxes, width, label='纳税额', color='#ff4d4f', alpha=0.8)
        ax1.bar([i + width/2 for i in x], after, width, label='到手金额', color='#52c41a', alpha=0.8)
        ax1.set_xticks(x)
        ax1.set_xticklabels(methods)
        ax1.set_ylabel('金额（元）')
        ax1.set_title(f'年终奖 {bonus:,.0f} 元 两种计税方式对比')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)

        for i, (t, a) in enumerate(zip(taxes, after)):
            ax1.text(i - width/2, t, f'{t:,.0f}', ha='center', va='bottom', fontsize=8)
            ax1.text(i + width/2, a, f'{a:,.0f}', ha='center', va='bottom', fontsize=8)

        ax2 = self.canvas.fig.add_subplot(122)
        max_b = max(bonus * 2, 200000)
        curve_data = generate_bonus_tax_curve(annual_taxable, max_b, step=max(max_b / 500, 100))
        ax2.plot(curve_data["bonus"], curve_data["separate_tax"], label='单独计税纳税额', color='#1890ff')
        ax2.plot(curve_data["bonus"], curve_data["combined_tax"], label='并入综合纳税额', color='#fa8c16')

        cps = find_bonus_critical_points()
        for cp in cps:
            if cp.boundary <= max_b:
                ax2.axvline(x=cp.boundary, color='red', linestyle='--', alpha=0.5, linewidth=0.8)
                ax2.axvspan(cp.boundary, min(cp.blind_spot_upper, max_b), alpha=0.1, color='red')
                ax2.text(cp.boundary, ax2.get_ylim()[1] * 0.9, f'{cp.boundary/10000:.1f}万',
                        fontsize=7, color='red', rotation=90, va='top')

        if bonus > 0:
            ax2.axvline(x=bonus, color='green', linestyle='-', alpha=0.7, linewidth=1.5)
            ax2.text(bonus, 0, f'当前\n{bonus/10000:.1f}万', fontsize=8, color='green',
                    ha='left', va='bottom')

        ax2.set_xlabel('年终奖金额（元）')
        ax2.set_ylabel('纳税额（元）')
        ax2.set_title('年终奖纳税额随金额变化（红色区间为陷阱）')
        ax2.legend()
        ax2.grid(alpha=0.3)

        self.canvas.fig.tight_layout()
        self.canvas.draw()


class CompareTab(QWidget):
    def __init__(self, monthly_tab: MonthlyCalcTab, parent=None):
        super().__init__(parent)
        self.monthly_tab = monthly_tab
        self.scenarios: List[ScenarioResult] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("从月度测算页获取基础数据，修改参数后添加为对比方案："))
        self.scenario_name_edit = QLineEdit("方案1")
        self.bonus_spin = QDoubleSpinBox()
        self.bonus_spin.setRange(0, 99999999)
        self.bonus_spin.setDecimals(2)
        self.bonus_spin.setSuffix(" 元")
        self.bonus_spin.setValue(0)
        self.bonus_spin.setSingleStep(1000)
        top_bar.addWidget(QLabel("方案名："))
        top_bar.addWidget(self.scenario_name_edit)
        top_bar.addWidget(QLabel("年终奖："))
        top_bar.addWidget(self.bonus_spin)

        self.bonus_method_combo = QComboBox()
        self.bonus_method_combo.addItems(["自动选择", "单独计税", "并入综合所得"])
        top_bar.addWidget(QLabel("年终奖计税方式："))
        top_bar.addWidget(self.bonus_method_combo)

        add_btn = QPushButton("添加当前方案")
        add_btn.setStyleSheet("background:#52c41a;color:white;padding:4px 12px;border-radius:3px;font-weight:bold")
        add_btn.clicked.connect(self._add_scenario)
        top_bar.addWidget(add_btn)

        clear_btn = QPushButton("清空全部方案")
        clear_btn.setStyleSheet("background:#ff4d4f;color:white;padding:4px 12px;border-radius:3px")
        clear_btn.clicked.connect(self._clear_scenarios)
        top_bar.addWidget(clear_btn)

        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.compare_table = QTableWidget()
        self.compare_table.setAlternatingRowColors(True)
        layout.addWidget(self.compare_table)

        self.canvas = MplCanvas(self, width=12, height=5)
        layout.addWidget(self.canvas)

    def _add_scenario(self):
        inputs = self.monthly_tab.get_monthly_inputs()
        bonus = self.bonus_spin.value()
        method_map = {"自动选择": "auto", "单独计税": "separate", "并入综合所得": "combined"}
        method = method_map.get(self.bonus_method_combo.currentText(), "auto")
        name = self.scenario_name_edit.text() or f"方案{len(self.scenarios)+1}"

        sr = run_scenario(name, inputs, bonus, method)
        self.scenarios.append(sr)
        self._refresh_table()
        self._draw_charts()

        self.scenario_name_edit.setText(f"方案{len(self.scenarios)+1}")

    def _clear_scenarios(self):
        self.scenarios.clear()
        self.compare_table.setRowCount(0)
        self.canvas.fig.clear()
        self.canvas.draw()

    def _refresh_table(self):
        if not self.scenarios:
            return
        cols = ["方案名", "年工资总额", "年终奖", "全年总纳税", "全年总到手",
                "综合税负率", "推荐计税方式", "年终奖节省"]
        self.compare_table.setColumnCount(len(cols))
        self.compare_table.setHorizontalHeaderLabels(cols)
        self.compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.compare_table.setRowCount(len(self.scenarios))

        for i, s in enumerate(self.scenarios):
            bonus = s.bonus_comparison.bonus if s.bonus_comparison else 0
            saving = s.bonus_comparison.tax_diff if s.bonus_comparison else 0
            method = s.bonus_comparison.better_method if s.bonus_comparison else "-"
            items = [
                s.name,
                f"{s.annual_result.total_salary:,.2f}",
                f"{bonus:,.2f}",
                f"{s.total_tax_with_bonus:,.2f}",
                f"{s.total_take_home_with_bonus:,.2f}",
                f"{s.effective_rate_with_bonus:.2f}%",
                method,
                f"{saving:,.2f}",
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.compare_table.setItem(i, j, item)

    def _draw_charts(self):
        if not self.scenarios:
            return
        self.canvas.fig.clear()

        ax1 = self.canvas.fig.add_subplot(121)
        names = [s.name for s in self.scenarios]
        taxes = [s.total_tax_with_bonus for s in self.scenarios]
        takes = [s.total_take_home_with_bonus for s in self.scenarios]
        x = range(len(names))
        width = 0.3
        ax1.bar([i - width/2 for i in x], taxes, width, label='总纳税', color='#ff4d4f', alpha=0.8)
        ax1.bar([i + width/2 for i in x], takes, width, label='总到手', color='#52c41a', alpha=0.8)
        ax1.set_xticks(x)
        ax1.set_xticklabels(names)
        ax1.set_ylabel('金额（元）')
        ax1.set_title('方案对比：总纳税 vs 总到手')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)

        ax2 = self.canvas.fig.add_subplot(122)
        rates = [s.effective_rate_with_bonus for s in self.scenarios]
        colors = ['#52c41a' if r == min(rates) else '#1890ff' for r in rates]
        bars = ax2.bar(names, rates, color=colors, alpha=0.8)
        ax2.set_ylabel('实际税负率（%）')
        ax2.set_title('方案对比：实际税负率')
        for bar, rate in zip(bars, rates):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{rate:.2f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)

        self.canvas.fig.tight_layout()
        self.canvas.draw()


class OptimizeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        input_bar = QHBoxLayout()
        input_bar.addWidget(QLabel("年度总包（工资+年终奖）："))
        self.total_spin = QDoubleSpinBox()
        self.total_spin.setRange(0, 99999999)
        self.total_spin.setDecimals(2)
        self.total_spin.setSuffix(" 元")
        self.total_spin.setValue(300000)
        self.total_spin.setSingleStep(10000)
        input_bar.addWidget(self.total_spin)

        input_bar.addWidget(QLabel("月五险一金："))
        self.si_spin = QDoubleSpinBox()
        self.si_spin.setRange(0, 9999999)
        self.si_spin.setDecimals(2)
        self.si_spin.setSuffix(" 元")
        self.si_spin.setValue(2500)
        input_bar.addWidget(self.si_spin)

        input_bar.addWidget(QLabel("月专项附加扣除："))
        self.spec_spin = QDoubleSpinBox()
        self.spec_spin.setRange(0, 9999999)
        self.spec_spin.setDecimals(2)
        self.spec_spin.setSuffix(" 元")
        self.spec_spin.setValue(0)
        input_bar.addWidget(self.spec_spin)

        calc_btn = QPushButton("优化计算")
        calc_btn.setStyleSheet(
            "QPushButton{background:#1890ff;color:white;font-size:14px;"
            "padding:6px 16px;border-radius:4px;font-weight:bold}"
            "QPushButton:hover{background:#40a9ff}"
        )
        calc_btn.clicked.connect(self._do_calc)
        input_bar.addWidget(calc_btn)
        input_bar.addStretch()
        layout.addLayout(input_bar)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet(
            "font-size:13px; padding:8px; background:#f6ffed; border-radius:4px; border:1px solid #b7eb8f;"
        )
        layout.addWidget(self.result_label)

        self.opt_table = QTableWidget()
        self.opt_table.setAlternatingRowColors(True)
        self.opt_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.opt_table)

        self.canvas = MplCanvas(self, width=12, height=5)
        layout.addWidget(self.canvas)

    def _do_calc(self):
        total = self.total_spin.value()
        si = self.si_spin.value()
        spec = self.spec_spin.value()

        results = optimize_income_split(total, si, spec)

        self._fill_table(results)
        self._draw_charts(results, total)

        if results:
            best = results[0]
            self.result_label.setText(
                f"💡 最优方案：年工资 {best.salary_annual:,.2f} 元 + 年终奖 {best.bonus_annual:,.2f} 元，"
                f"总纳税 {best.total_tax:,.2f} 元，总到手 {best.total_take_home:,.2f} 元，"
                f"实际税负率 {best.effective_rate:.2f}%"
            )

    def _fill_table(self, results: List[OptimizationSplit]):
        cols = ["年工资", "年终奖", "工资纳税", "年终奖纳税",
                "总纳税", "总到手", "实际税负率"]
        self.opt_table.setColumnCount(len(cols))
        self.opt_table.setHorizontalHeaderLabels(cols)
        self.opt_table.setRowCount(len(results))

        min_tax = min(r.total_tax for r in results) if results else 0

        for i, r in enumerate(results):
            items = [
                f"{r.salary_annual:,.2f}",
                f"{r.bonus_annual:,.2f}",
                f"{r.salary_tax:,.2f}",
                f"{r.bonus_tax:,.2f}",
                f"{r.total_tax:,.2f}",
                f"{r.total_take_home:,.2f}",
                f"{r.effective_rate:.2f}%",
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if r.total_tax == min_tax:
                    item.setBackground(QColor(246, 255, 237))
                self.opt_table.setItem(i, j, item)

    def _draw_charts(self, results: List[OptimizationSplit], total: float):
        if not results:
            return
        self.canvas.fig.clear()

        ax1 = self.canvas.fig.add_subplot(121)
        bonuses = [r.bonus_annual / 10000 for r in results]
        salary_taxes = [r.salary_tax for r in results]
        bonus_taxes = [r.bonus_tax for r in results]
        total_taxes = [r.total_tax for r in results]

        ax1.plot(bonuses, salary_taxes, 'o-', label='工资纳税', color='#1890ff', markersize=4)
        ax1.plot(bonuses, bonus_taxes, 's-', label='年终奖纳税', color='#fa8c16', markersize=4)
        ax1.plot(bonuses, total_taxes, '^-', label='总纳税', color='#ff4d4f', markersize=5, linewidth=2)

        best = min(results, key=lambda x: x.total_tax)
        ax1.axvline(x=best.bonus_annual / 10000, color='green', linestyle='--', alpha=0.7)
        ax1.annotate(f'最优: 年终奖{best.bonus_annual/10000:.1f}万',
                    xy=(best.bonus_annual / 10000, best.total_tax),
                    fontsize=9, color='green', fontweight='bold')

        ax1.set_xlabel('年终奖金额（万元）')
        ax1.set_ylabel('纳税额（元）')
        ax1.set_title(f'总包 {total/10000:.0f}万 工资与年终奖分配优化')
        ax1.legend()
        ax1.grid(alpha=0.3)

        ax2 = self.canvas.fig.add_subplot(122)
        takes = [r.total_take_home for r in results]
        rates = [r.effective_rate for r in results]

        ax2_twin = ax2.twinx()
        line1 = ax2.plot(bonuses, takes, 'o-', label='总到手', color='#52c41a', markersize=4)
        line2 = ax2_twin.plot(bonuses, rates, 's-', label='税负率', color='#722ed1', markersize=4)

        ax2.set_xlabel('年终奖金额（万元）')
        ax2.set_ylabel('到手金额（元）', color='#52c41a')
        ax2_twin.set_ylabel('实际税负率（%）', color='#722ed1')

        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax2.legend(lines, labels, loc='center right')
        ax2.set_title('到手与税负率随年终奖分配变化')
        ax2.grid(alpha=0.3)

        self.canvas.fig.tight_layout()
        self.canvas.draw()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("个人所得税测算与筹划工具 — 累计预扣法 · 年终奖筹划 · 方案对比")
        self.setMinimumSize(1280, 800)
        self._init_ui()
        self._init_menu()

    def _init_ui(self):
        self.tabs = QTabWidget()
        self.monthly_tab = MonthlyCalcTab()
        self.bonus_tab = BonusPlanTab(self.monthly_tab)
        self.compare_tab = CompareTab(self.monthly_tab)
        self.optimize_tab = OptimizeTab()

        self.tabs.addTab(self.monthly_tab, "📊 月度测算")
        self.tabs.addTab(self.bonus_tab, "💰 年终奖筹划")
        self.tabs.addTab(self.compare_tab, "⚖ 方案对比")
        self.tabs.addTab(self.optimize_tab, "🧠 收入结构优化")

        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("就绪 | 所有计算均在本地完成，无需联网")

    def _init_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")

        save_action = QAction("保存方案...", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_scenario)
        file_menu.addAction(save_action)

        load_action = QAction("加载方案...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_scenario)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        export_action = QAction("导出报告...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._export_report)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _save_scenario(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存方案", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        state = {
            "monthly": self.monthly_tab.get_state(),
            "bonus": self.bonus_tab.bonus_spin.value(),
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        self.statusBar().showMessage(f"方案已保存到 {path}", 3000)

    def _load_scenario(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载方案", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        if "monthly" in state:
            self.monthly_tab.set_state(state["monthly"])
        if "bonus" in state:
            self.bonus_tab.bonus_spin.setValue(state["bonus"])
        self.statusBar().showMessage(f"方案已从 {path} 加载", 3000)

    def _export_report(self):
        scenarios = self.compare_tab.scenarios
        if not scenarios:
            inputs = self.monthly_tab.get_monthly_inputs()
            annual = calc_annual(inputs)
            bonus = self.bonus_tab.bonus_spin.value()
            sr = run_scenario("当前方案", inputs, bonus)
            scenarios = [sr]

        critical_points = find_bonus_critical_points()
        report = export_report(scenarios, critical_points)

        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)
        self.statusBar().showMessage(f"报告已导出到 {path}", 3000)

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于",
            "个人所得税测算与筹划工具 v1.0\n\n"
            "基于中国2019年新个税法\n"
            "· 累计预扣法逐月测算\n"
            "· 年终奖单独/并入综合计税对比\n"
            "· 临界陷阱检测与避坑提示\n"
            "· 多方案对比与收入结构优化\n\n"
            "所有计算均在本地完成，无需联网。\n"
            "税率表及扣除标准内置，仅供参考。"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    palette = app.palette()
    palette.setColor(palette.Window, QColor(250, 250, 250))
    palette.setColor(palette.WindowText, QColor(33, 33, 33))
    palette.setColor(palette.Base, QColor(255, 255, 255))
    palette.setColor(palette.AlternateBase, QColor(245, 245, 245))
    palette.setColor(palette.Highlight, QColor(24, 144, 255))
    palette.setColor(palette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
