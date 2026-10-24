import unittest

import sympy as sp

from calc_term import CalcError, Calculator, ZERO


class ExactArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_decimals_are_exact(self):
        self.assertEqual(self.calc.calculate("0.1+0.2"), "3/10")
        self.assertEqual(self.calc.calculate("0.1+0.2-0.3"), "0")
        self.assertEqual(self.calc.calculate("1e-100 + 2e-100"), str(sp.Rational(3, 10**100)))
        value = self.calc.evaluate("0." + "1234567890" * 20)
        self.assertEqual(value.value, sp.Rational("0." + "1234567890" * 20))
        self.assertFalse(value.value.atoms(sp.Float))

    def test_large_integer_and_cancellation(self):
        value = self.calc.evaluate("10^1000 + 1 - 10^1000")
        self.assertEqual(value.value, 1)
        self.assertEqual(self.calc.evaluate("2^256").value, 2**256)

    def test_integer_beyond_pythons_default_string_limit(self):
        literal = "9" * 4500
        self.assertEqual(self.calc.calculate(literal + "+1"), "1" + "0" * 4500)

    def test_fractions(self):
        self.assertEqual(self.calc.calculate("1/3 + 1/6"), "1/2")
        self.assertEqual(self.calc.calculate("1/7 * 7"), "1")

    def test_underscores_group_integer_digits_and_history_omits_them(self):
        self.assertEqual(self.calc.calculate("1_000 + 2_500"), "3500")
        self.assertEqual(self.calc.history[-1].line, "1000 + 2500 = 3500")
        self.assertEqual(self.calc.calculate("-1_000 + 25_00"), "1500")
        self.assertEqual(self.calc.calculate("1_000->x"), "1000")
        self.assertEqual(self.calc.history[-1].source, "1000->x")
        self.assertEqual(self.calc.calculate("2*x"), "2000")

    def test_grouped_fractions_decimals_and_exponents_stay_exact(self):
        for source, expected in {"1/1_000": "1/1000", "1_000/2_000": "1/2",
                                 "1_000.25": "4001/4", "0.1_25": "1/8",
                                 "1_000e-3": "1", "1e1_0": "10000000000"}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
                self.assertNotIn("_", self.calc.history[-1].line)

    def test_grouped_arbitrary_precision_integer(self):
        literal = "9" + "_999" * 1500
        value = self.calc.evaluate(literal + "+1").value
        self.assertEqual(str(value), "1" + "0" * 4501)
        self.assertFalse(value.atoms(sp.Float))
        self.assertNotIn("_", self.calc.history[-1].source)

    def test_malformed_digit_separators_are_rejected(self):
        for source in ["1__000", "1_", "_1_000", "1_ 000", "1_.0", "1._0",
                       "1e_3", "1e3_", "1/1__000", "1_000->x1_000"]:
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source)
            self.assertEqual(self.calc.history[-1].source, source)
            self.assertTrue(self.calc.history[-1].is_error)

    def test_binary_octal_and_hexadecimal_literals(self):
        for source, expected in {"0b1010": "10", "0o17": "15", "0h3FA2": "16290",
                                 "0H3fa2": "16290", "0B1010": "10", "0O17": "15",
                                 "0b0": "0", "0h00": "0", "0o000": "0",
                                 "-0hFF": "-255", "0h1e3": "483"}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
                self.assertEqual(self.calc.history[-1].source, expected)

    def test_base_literals_in_arithmetic_fractions_and_assignment(self):
        self.assertEqual(self.calc.calculate("0b1010 + 0o17 + 0hFF"), "280")
        self.assertEqual(self.calc.history[-1].line, "10 + 15 + 255 = 280")
        self.assertEqual(self.calc.calculate("1/0b1000"), "1/8")
        self.assertEqual(self.calc.calculate("0hFF->x"), "255")
        self.assertEqual(self.calc.history[-1].source, "255->x")
        self.assertEqual(self.calc.calculate("x+1"), "256")
        self.assertEqual(self.calc.calculate("0b10^0o3"), "8")

    def test_grouped_base_literals(self):
        for source, expected in {"0b1010_0101": "165", "0o1_234": "668",
                                 "0h3F_A2": "16290", "0hDEAD_BEEF": "3735928559"}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
                self.assertEqual(self.calc.history[-1].line, expected + " = " + expected)

    def test_large_base_literal_is_exact(self):
        value = self.calc.evaluate("0h" + "F" * 4000 + "+1").value
        self.assertEqual(value, 1 << 16000)
        self.assertFalse(value.atoms(sp.Float))

    def test_invalid_base_literals_are_rejected_without_mutating_state(self):
        self.calc.evaluate("3->x")
        for source in ["0b", "0h", "0o", "0b102", "0o8", "0hG", "0h3FA2G",
                       "0b_101", "0h_FF", "0o_10", "0hF__0", "0b1_2", "0o1_8",
                       "0hF.5", ".0hF", "0b10e3", "0hF_", "0hG->x"]:
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source)
        self.assertEqual(self.calc.calculate("x"), "3")
        self.assertEqual(sum(not entry.is_error for entry in self.calc.history), 2)
        self.assertEqual(self.calc.answer.value, 3)

    def test_base_prefix_inside_variable_name_is_preserved(self):
        self.calc.evaluate("2->value0hFF")
        self.assertEqual(self.calc.calculate("value0hFF+0b10"), "4")
        self.assertEqual(self.calc.history[-1].source, "value0hFF+2")

    def test_operator_precedence(self):
        for source, expected in {"2+3*4": 14, "(2+3)*4": 20, "2^3^2": 512,
                                 "-2^2": -4, "2^-3": sp.Rational(1, 8), "7%4": 3,
                                 "3!+1": 7, "2(3+4)": 14, "2**3": 8}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.evaluate(source).value, expected)

    def test_bitwise_operators(self):
        for source, expected in {
            "5&3": 1, "5|3": 7, "5 xor 3": 6, "~5": -6,
            "5<<2": 20, "20>>2": 5, "5<<0": 5, "5>>0": 5,
            "~0": -1, "~-1": 0, "~~5": 5, "-5&3": 3,
            "-5|3": -5, "-5 xor 3": -8, "-5>>1": -3, "-5<<1": -10,
            "0hFF&0b1010": 10, "0o17 xor 0b1010": 5, "6/3&3": 2,
        }.items():
            with self.subTest(source=source):
                value = self.calc.evaluate(source)
                self.assertEqual(value.value, expected)
                self.assertIsInstance(value.value, sp.Integer)
                self.assertEqual(value.dims, ZERO)

    def test_bitwise_precedence(self):
        for source, expected in {
            "1|2 xor 3": 1, "6 xor 3&1": 7, "6&1<<1": 2,
            "1<<1+2": 8, "32>>1+2": 4, "1<<2*3": 64,
            "8>>1>>1": 2, "1<<1<<2": 8, "2^3&3": 0,
            "~2^2": -5, "2^~1": sp.Rational(1, 4), "~3!": -7,
            "(1|2) xor 3": 0, "(6 xor 3)&1": 1,
        }.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.evaluate(source).value, expected)
        for source in ["5&3==1", "5 xor 3==6", "1<<2<8", "0<5&3<2", "20>>2>=5"]:
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), "True")

    def test_bitwise_arbitrary_precision_and_output_modes(self):
        for mode in ("exact", "approximate"):
            self.calc.set_output_mode(mode)
            self.assertEqual(self.calc.evaluate("1<<1000").value, 1 << 1000)
            self.assertEqual(self.calc.calculate("(1<<1000)|1"), str((1 << 1000) | 1))
            self.assertEqual(self.calc.evaluate("~(1<<1000)").value, ~(1 << 1000))
            self.assertEqual(self.calc.calculate("(1<<1000)>>999"), "2")

    def test_bitwise_assignments_ans_history_and_names(self):
        self.assertEqual(self.calc.calculate("0b1010|0h05->mask"), "15")
        self.assertEqual(self.calc.history[-1].line, "10|5->mask = 15")
        self.assertEqual(self.calc.calculate("ans xor 3"), "12")
        self.assertEqual(self.calc.calculate("mask&7"), "7")
        self.assertEqual(self.calc.calculate("~mask"), "-16")
        self.assertEqual(self.calc.calculate(self.calc.history[-1].result), "-16")
        self.calc.evaluate("2->xorValue")
        self.assertEqual(self.calc.calculate("xorValue xor 3"), "1")

    def test_invalid_bitwise_operands_preserve_state(self):
        self.calc.evaluate("3->x")
        for op in ("&", "|", "xor", "<<", ">>"):
            for operand in ("1/2", "1_m", "True", "[1,2]", "i", "y", "approx(2)"):
                for source in (f"({operand}) {op} 1->x", f"1 {op} ({operand})->x"):
                    with self.subTest(source=source), self.assertRaisesRegex(CalcError, "dimensionless exact integers"):
                        self.calc.evaluate(source)
                    self.assertEqual(self.calc.answer.value, 3)
                    self.assertEqual(self.calc.variables["x"].value, 3)
                    self.assertTrue(self.calc.history[-1].is_error)
        for operand in ("1/2", "1_m", "True", "[1,2]", "i", "y", "approx(2)"):
            with self.subTest(operand=operand), self.assertRaisesRegex(CalcError, "dimensionless exact integers"):
                self.calc.evaluate(f"~({operand})")

    def test_invalid_bitwise_syntax_and_shift_counts(self):
        for source in ("1<<-1", "1>>-1"):
            with self.subTest(source=source), self.assertRaisesRegex(CalcError, "nonnegative"):
                self.calc.evaluate(source)
        for source in ("1&", "|2", "~", "5 xor", "xor", "1||2", "2->xor",
                       "1=>1<<1", "1=>1|1", "1=>~1"):
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source)

    def test_assignment_and_case_sensitive_names(self):
        self.assertEqual(self.calc.calculate("3->x"), "3")
        self.assertEqual(self.calc.history[-1].line, "3->x = 3")
        self.assertEqual(self.calc.calculate("4*x"), "12")
        self.calc.evaluate("7->X")
        self.assertEqual(self.calc.evaluate("x+X").value, 10)
        self.calc.evaluate("0.1->ε")
        self.assertEqual(self.calc.evaluate("3*ε").value, sp.Rational(3, 10))

    def test_comparison_operators(self):
        for source, expected in {
            "3>6": "False", "6>3": "True", "3<6": "True", "6<3": "False",
            "3>=3": "True", "3>=6": "False", "3<=3": "True", "6<=3": "False",
            "3=3": "True", "3=6": "False", "3==3": "True", "3==6": "False",
            "3!=6": "True", "3!=3": "False", "3≤6": "True", "6≥3": "True",
            "3≠6": "True", "0.1+0.2==0.3": "True", "sqrt(2)^2=2": "True",
            "i!=0": "True", "i==i": "True", "0hFF>0b10": "True",
        }.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
                self.assertEqual(self.calc.answer.dims, ZERO)
                self.assertIs(self.calc.answer.value, sp.true if expected == "True" else sp.false)

    def test_comparison_precedence_and_chaining(self):
        for source, expected in {
            "2+3*4>10+3": "True", "-2^2 < -3": "True", "3! != 5": "True",
            "3! == 6": "True", "2(3+4)<=14": "True", "1<2<=2!=3": "True",
            "3>2>1": "True", "3<2<1": "False", "1<3<2": "False",
            "1=1==1": "True", "(3>6)==False": "True",
        }.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)

    def test_comparisons_with_units(self):
        for source, expected in {
            "1_m == 100_cm": "True", "1_ft<1_m": "True", "2_m>=3_m": "False",
            "32_°F=0_°C": "True", "0_°C<40_°F": "True", "1_m!=1_ft": "True",
            "1_m<150_cm<2_m": "True",
        }.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)

    def test_booleans_in_history_assignment_ans_and_approximate_output(self):
        self.assertEqual(self.calc.calculate("3>6->flag"), "False")
        self.assertEqual(self.calc.history[-1].line, "3>6->flag = False")
        self.assertEqual(self.calc.calculate("ans==False"), "True")
        self.assertEqual(self.calc.calculate("flag"), "False")
        self.assertEqual(self.calc.calculate(self.calc.history[-1].result), "False")
        self.calc.set_output_mode("approximate")
        self.assertEqual(self.calc.calculate("1/3<1/2"), "True")
        self.assertEqual(self.calc.calculate("ans"), "True")
        self.assertEqual(self.calc.calculate("False"), "False")

    def test_invalid_comparisons_preserve_state(self):
        self.calc.evaluate("3->x")
        for source in ["1_m<1_s", "1_m=1", "1_m!=1_s", "y<3", "y=3", "i>0",
                       "[1,2]==[1,2]", "True<False", "3>", "3===3", "3! = =6",
                       "(3>6)+1", "-True", "True_m", "True=>1", "3->True",
                       "sin(3>6)", "3<1/0", "1_m>2_s->x"]:
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source)
            self.assertEqual(self.calc.answer.value, 3)
            self.assertEqual(self.calc.variables["x"].value, 3)
        self.assertEqual(self.calc.calculate("y=y"), "True")

    def test_unicode_operators(self):
        self.assertEqual(self.calc.calculate("3→x"), "3")
        self.assertEqual(self.calc.calculate("3_in⇒_ft"), "1/4_ft")
        self.assertEqual(self.calc.calculate("2×3−4÷2"), "4")
        self.assertEqual(self.calc.calculate("(2+3)²"), "25")

    def test_ans(self):
        self.calc.evaluate("1/3")
        self.assertEqual(self.calc.calculate("3*ans"), "1")
        self.assertEqual(self.calc.calculate("ans+ans->x"), "2")
        with self.assertRaises(CalcError):
            self.calc.evaluate("1/0->x")
        self.assertEqual(self.calc.calculate("ans*5"), "10")
        self.assertEqual(self.calc.variables["x"].value, 2)
        self.assertEqual(self.calc.calculate("ans+1"), "11")

    def test_ans_preserves_units_and_solution_lists(self):
        self.calc.evaluate("12_in=>_ft")
        self.assertEqual(self.calc.calculate("2*ans"), "2_ft")
        self.calc.evaluate("solve(x^2-4,x)")
        self.assertEqual(self.calc.calculate("ans"), "[-2, 2]")

    def test_symbolic_operations(self):
        y = sp.Symbol("y")
        samples = {"expand((y+1)^2)": sp.Add(y**2, sp.Mul(2, y), 1),
                   "factor(y^2-1)": sp.Mul(sp.Add(y, -1), sp.Add(y, 1)),
                   "simplify((y^2-1)/(y-1))": sp.Add(y, 1),
                   "diff(y^3,y)": sp.Mul(3, y**2),
                   "diff(y^4,y,2)": sp.Mul(12, y**2),
                   "integrate(y^2,y)": sp.Mul(y**3, sp.Rational(1, 3)),
                   "integrate(y^2,y,0,3)": 9,
                   "subs(y^2+1,y,3)": 10}
        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.evaluate(source).value, expected)
        self.assertEqual(self.calc.calculate("solve(y^2-4,y)"), "[-2, 2]")
        self.assertEqual(self.calc.calculate("solve(y_m-3_m,y)"), "[3]")

    def test_solution_lists_can_be_recalled_and_reparsed(self):
        result = self.calc.calculate("solve(y^2-2,y)")
        self.assertEqual(self.calc.calculate(result), result)
        self.assertEqual(self.calc.calculate("[]"), "[]")
        with self.assertRaises(CalcError):
            self.calc.calculate("sin([-2,2])")

    def test_symbolic_assignment(self):
        self.calc.evaluate("y+1->x")
        self.assertEqual(self.calc.evaluate("x^2").value, sp.Add(sp.Symbol("y"), 1)**2)

    def test_radians_and_degrees(self):
        self.assertEqual(self.calc.calculate("sin(pi/2)"), "1")
        self.assertEqual(self.calc.calculate("asin(1)"), "pi/2")
        self.calc.set_mode("degree")
        self.assertEqual(self.calc.calculate("sin(30)"), "1/2")
        self.assertEqual(self.calc.calculate("cos(60)"), "1/2")
        self.assertEqual(self.calc.calculate("asin(1)"), "90")
        # Hyperbolic functions do not use the angle setting.
        self.assertEqual(self.calc.evaluate("sinh(1)").value, sp.sinh(1))
        with self.assertRaises(CalcError):
            self.calc.set_mode("invalid")

    def test_exact_transcendentals_and_explicit_precision(self):
        self.assertEqual(self.calc.calculate("sqrt(2)"), "sqrt(2)")
        self.assertEqual(self.calc.calculate("cbrt(-8)"), "-2")
        self.assertEqual(self.calc.calculate("ln(e)"), "1")
        self.assertEqual(self.calc.calculate("log(100)"), "2")
        self.assertEqual(self.calc.calculate("log(8,2)"), "3")
        exact = self.calc.evaluate("pi").value
        self.assertFalse(exact.atoms(sp.Float))
        approximation = self.calc.evaluate("approx(pi,120)").value
        self.assertGreaterEqual(approximation._prec, 395)
        self.assertEqual(approximation, sp.N(sp.pi, 120))
        self.calc.set_precision(80)
        self.assertEqual(self.calc.evaluate("approx(sqrt(2))").value, sp.N(sp.sqrt(2), 80))
        self.assertEqual(self.calc.calculate("0.1+0.2"), "3/10")

    def test_history_cap_includes_errors_without_changing_ans(self):
        for i in range(35):
            self.calc.evaluate(str(i))
        self.assertEqual(len(self.calc.history), 30)
        self.assertEqual(self.calc.history[0].source, "5")
        self.assertEqual(self.calc.history[-1].source, "34")
        with self.assertRaises(CalcError):
            self.calc.evaluate("1/0")
        self.assertEqual(len(self.calc.history), 30)
        self.assertEqual(self.calc.history[0].source, "6")
        self.assertTrue(self.calc.history[-1].is_error)
        self.assertEqual(self.calc.history[-1].line, "1/0 = Error: Division by zero.")
        self.assertEqual(self.calc.answer.value, 34)

    def test_blank_and_unrecorded_errors_do_not_add_history(self):
        for source, record in [("  ", True), ("0hG", False), ("1/0", False)]:
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source, record=record)
        self.assertFalse(self.calc.history)

    def test_default_output_modes_and_validation(self):
        self.assertEqual(self.calc.output_mode, "exact")
        self.assertEqual(self.calc.calculate("1/3"), "1/3")
        self.calc.set_output_mode("approx")
        self.assertEqual(self.calc.output_mode, "approximate")
        for invalid in ("invalid", "degree", None):
            with self.subTest(mode=invalid), self.assertRaises(CalcError):
                self.calc.set_output_mode(invalid)
        self.assertEqual(self.calc.output_mode, "approximate")
        with self.assertRaises(CalcError):
            Calculator(output_mode="invalid")

    def test_approximate_output_for_fractions_irrationals_and_decimals(self):
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(12)
        for source, expected in {"1/3": "0.333333333333", "sqrt(2)": "1.41421356237",
                                 "pi": "3.14159265359", "0.1+0.2": "0.3"}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
                self.assertEqual(self.calc.history[-1].result, expected)

    def test_approximate_output_keeps_assignments_and_ans_exact(self):
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(5)
        self.assertEqual(self.calc.calculate("1/3->x"), "0.33333")
        self.assertEqual(self.calc.variables["x"].value, sp.Rational(1, 3))
        self.assertEqual(self.calc.answer.value, sp.Rational(1, 3))
        self.assertEqual(self.calc.calculate("ans*3"), "1")
        self.assertEqual(self.calc.calculate("x*3"), "1")
        self.calc.set_output_mode("exact")
        self.assertEqual(self.calc.calculate("x"), "1/3")
        self.assertEqual(self.calc.history[0].result, "0.33333")

    def test_per_calculation_approximation_preserves_mode_and_exact_state(self):
        for mode in ("exact", "approximate"):
            with self.subTest(mode=mode):
                self.calc.set_output_mode(mode)
                self.calc.set_precision(6)
                self.assertEqual(self.calc.calculate("1/3->x", approximate=True), "0.333333")
                self.assertEqual(self.calc.history[-1].result, "0.333333")
                self.assertEqual(self.calc.history[-1].source, "1/3->x")
                self.assertEqual(self.calc.variables["x"].value, sp.Rational(1, 3))
                self.assertEqual(self.calc.answer.value, sp.Rational(1, 3))
                self.assertEqual(self.calc.output_mode, mode)
                self.assertEqual(self.calc.calculate("x*3"), "1")
                self.assertEqual(self.calc.calculate("x"), "1/3" if mode == "exact" else "0.333333")

    def test_per_calculation_approximation_supports_units_lists_and_errors(self):
        self.calc.set_precision(6)
        for source, expected in {"sqrt(2)": "1.41421", "3_in=>_ft": "0.25_ft",
                                 "solve(y^2-2,y)": "[-1.41421, 1.41421]", "True": "True"}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source, approximate=True), expected)
                self.assertEqual(self.calc.output_mode, "exact")
        self.calc.calculate("7->x")
        with self.assertRaises(CalcError):
            self.calc.calculate("1/0->x", approximate=True)
        self.assertEqual(self.calc.variables["x"].value, 7)
        self.assertEqual(self.calc.answer.value, 7)
        self.assertEqual(self.calc.output_mode, "exact")
        self.assertTrue(self.calc.history[-1].is_error)

    def test_approximate_output_supports_arbitrary_precision(self):
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(120)
        result = self.calc.calculate("pi")
        self.assertEqual(result, str(sp.N(sp.pi, 120)))
        self.assertGreater(len(result), 100)
        self.assertEqual(self.calc.answer.value, sp.pi)
        self.calc.set_precision(3)
        integer = "1" + "0" * 5000 + "1"
        self.assertEqual(self.calc.calculate(integer), integer)

    def test_explicit_approx_precision_overrides_default_output_precision(self):
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(12)
        for digits in (5, 100):
            with self.subTest(digits=digits):
                result = self.calc.calculate(f"approx(pi,{digits})")
                self.assertEqual(result, str(sp.N(sp.pi, digits)))
                self.assertEqual(self.calc.calculate(f"approx(i*pi,{digits})"), result + "*I")
                self.assertEqual(self.calc.calculate(f"approx(pi,{digits})*y"), result + "*y")

    def test_approximate_output_supports_symbolic_expressions_and_solution_lists(self):
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(12)
        self.assertEqual(self.calc.calculate("pi*y"), "3.14159265359*y")
        self.assertEqual(self.calc.calculate("solve(y^2-2,y)"), "[-1.41421356237, 1.41421356237]")
        self.assertEqual(self.calc.calculate("solve(y^2-4,y)"), "[-2, 2]")
        self.assertEqual(self.calc.calculate("[]"), "[]")

    def test_approximate_output_converts_units_before_rounding(self):
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(12)
        self.assertEqual(self.calc.calculate("3_in=>_ft"), "0.25_ft")
        self.assertEqual(self.calc.calculate("1_°C=>_°F"), "33.8_°F")
        compound = self.calc.calculate("sqrt(2)*_m/_s")
        self.assertIn("1.41421356237", compound)
        self.assertEqual(self.calc.parse(compound).dims, self.calc.answer.dims)
        self.calc.define_unit("thirdmeter", "1/3_m")
        self.assertEqual(self.calc.registry.get("thirdmeter").scale, sp.Rational(1, 3))
        self.assertEqual(self.calc.unit_definitions["thirdmeter"], "1/3_m")
        self.assertEqual(self.calc.calculate("3_thirdmeter=>_m"), "1_m")

    def test_failed_assignment_does_not_mutate_state(self):
        self.calc.evaluate("3->x")
        with self.assertRaises(CalcError):
            self.calc.evaluate("1/0->x")
        self.assertEqual(self.calc.variables["x"].value, 3)
        self.assertEqual(self.calc.answer.value, 3)
        self.assertEqual(len(self.calc.history), 2)
        self.assertTrue(self.calc.history[-1].is_error)

    def test_invalid_math_and_unsafe_python_are_rejected(self):
        sources = ["", "1/0", "0^-1", "ln(0)", "1%0", "(1+2", "1+", "sin()", "sin(1,2)",
                   "factorial(-1)", "approx(pi,1)", "approx(pi,2_m)", "diff(x,3)",
                   "3->pi", "3->ans", "3->1x", "3->x->y", "solve(x^2-4,x)+1",
                   "__import__('os').system('echo bad')", "x.__class__", "[1,]", "[1_m,2_s]", "lambda x: x"]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source)

    def test_dimensionless_result(self):
        value = self.calc.evaluate("2_m/1_m")
        self.assertEqual(value.value, 2)
        self.assertEqual(value.dims, ZERO)


class EquationTests(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_equations_support_implicit_multiplication_and_expression_arguments(self):
        self.calc.define_equation("y1", "4x")
        for source, expected in {"y1(3)": "12", "y1(1/3)": "4/3",
                                 "2y1(3)+1": "25", "y1(2+1)": "12",
                                 "y1(y1(3))": "48", "y1(t+1)": "4*t + 4"}.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
        self.assertEqual(self.calc.history[-1].source, "y1(t+1)")

    def test_local_x_does_not_use_or_change_session_x(self):
        self.calc.calculate("100->x")
        self.calc.define_equation("y1", "x^2+1")
        self.assertEqual(self.calc.answer.value, 100)
        self.assertEqual(len(self.calc.history), 1)
        self.assertEqual(self.calc.calculate("y1(3)"), "10")
        self.assertEqual(self.calc.calculate("x"), "100")
        self.assertEqual(self.calc.calculate("y1(2)->a"), "5")
        self.assertEqual(self.calc.calculate("a+ans"), "10")

    def test_forward_references_resolve_current_definitions_with_local_arguments(self):
        self.calc.define_equation("y99", "y1(x+1)+x")
        with self.assertRaisesRegex(CalcError, "y1.*not defined"):
            self.calc.calculate("y99(3)")
        self.calc.define_equation("y1", "4x")
        self.assertEqual(self.calc.calculate("y99(3)"), "19")
        self.calc.define_equation("y1", "2x")
        self.assertEqual(self.calc.calculate("y99(3)"), "11")
        self.assertNotIn("x", self.calc.variables)

    def test_equations_follow_angle_and_output_modes(self):
        self.calc.define_equation("y1", "sin(x)")
        self.calc.set_mode("degree")
        self.assertEqual(self.calc.calculate("y1(30)"), "1/2")
        self.calc.set_mode("radian")
        self.assertEqual(self.calc.calculate("y1(pi/6)"), "1/2")
        self.calc.define_equation("y2", "x/3")
        self.calc.set_output_mode("approximate")
        self.calc.set_precision(6)
        self.assertEqual(self.calc.calculate("y2(1)"), "0.333333")
        self.assertEqual(self.calc.answer.value, sp.Rational(1, 3))

    def test_bad_definitions_preserve_previous_formula_and_state(self):
        self.calc.calculate("7->x")
        self.calc.define_equation("y1", "4x")
        for formula in ("4x+", "x->a", "1/0", "[x,1]", "True", "y2()", "x.__class__"):
            with self.subTest(formula=formula), self.assertRaises(CalcError):
                self.calc.define_equation("y1", formula)
            self.assertEqual(self.calc.equations["y1"], "4x")
            self.assertEqual(self.calc.answer.value, 7)
            self.assertEqual(len(self.calc.history), 1)

    def test_undefined_circular_and_bad_calls_leave_ans_and_assignments_intact(self):
        self.calc.calculate("7->x")
        self.calc.define_equation("y1", "y2(x)")
        self.calc.define_equation("y2", "y1(x)")
        for source, error in (("y99(3)", "not defined"), ("y1(3)", "Circular"),
                              ("y1()", "arguments"), ("y1(1,2)", "arguments"),
                              ("y1(True)", "scalar"), ("y1(1_m)", "dimensionless"),
                              ("y1", "call an equation"), ("3->y1", "reserved")):
            with self.subTest(source=source), self.assertRaisesRegex(CalcError, error):
                self.calc.calculate(source)
            self.assertEqual(self.calc.answer.value, 7)
            self.assertEqual(self.calc.variables["x"].value, 7)
            self.assertTrue(self.calc.history[-1].is_error)
        self.calc.define_equation("y1", "y1(x)")
        with self.assertRaisesRegex(CalcError, "Circular"):
            self.calc.calculate("y1(3)")

    def test_all_99_slots_and_clearing(self):
        for i in range(1, 100):
            self.calc.define_equation(f"y{i}", f"{i}x")
            self.assertEqual(self.calc.calculate(f"y{i}(2)"), str(2 * i))
        for name in ("y0", "y100", "y01", "Y1", "sin"):
            with self.subTest(name=name), self.assertRaises(CalcError):
                self.calc.define_equation(name, "4x")
        self.calc.define_equation("y1", "  ")
        with self.assertRaisesRegex(CalcError, "not defined"):
            self.calc.calculate("y1(3)")


if __name__ == "__main__":
    unittest.main()
