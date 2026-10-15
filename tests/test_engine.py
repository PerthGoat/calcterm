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
        self.assertFalse(self.calc.history)

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
        self.assertEqual(len(self.calc.history), 2)

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

    def test_assignment_and_case_sensitive_names(self):
        self.assertEqual(self.calc.calculate("3->x"), "3")
        self.assertEqual(self.calc.history[-1].line, "3->x = 3")
        self.assertEqual(self.calc.calculate("4*x"), "12")
        self.calc.evaluate("7->X")
        self.assertEqual(self.calc.evaluate("x+X").value, 10)
        self.calc.evaluate("0.1->ε")
        self.assertEqual(self.calc.evaluate("3*ε").value, sp.Rational(3, 10))

    def test_unicode_operators(self):
        self.assertEqual(self.calc.calculate("3→x"), "3")
        self.assertEqual(self.calc.calculate("3_in⇒_ft"), "1/4_ft")
        self.assertEqual(self.calc.calculate("2×3−4÷2"), "4")
        self.assertEqual(self.calc.calculate("(2+3)²"), "25")

    def test_ans(self):
        self.calc.evaluate("1/3")
        self.assertEqual(self.calc.calculate("3*ans"), "1")

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

    def test_history_cap_and_successful_entries(self):
        for i in range(35):
            self.calc.evaluate(str(i))
        self.assertEqual(len(self.calc.history), 30)
        self.assertEqual(self.calc.history[0].source, "5")
        self.assertEqual(self.calc.history[-1].source, "34")
        before = list(self.calc.history)
        with self.assertRaises(CalcError):
            self.calc.evaluate("1/0")
        self.assertEqual(list(self.calc.history), before)
        self.assertEqual(self.calc.answer.value, 34)

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
        self.assertEqual(len(self.calc.history), 1)

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


if __name__ == "__main__":
    unittest.main()
