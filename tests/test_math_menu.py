"""Integration checks for the built-in Math menu and the expressions it inserts."""

import tempfile
import unittest
from pathlib import Path

from calcterm.app import ConsoleApp
from calcterm.core import CalcError, sp
from calcterm.engine import COMMANDS, FUNCTIONS, Calculator, TOKEN, normalize_input
from calcterm.math_menu_data import MATH_MENU
from calcterm.menus import math_item_kind, validate_menus


class MathMenuTests(unittest.TestCase):
    def test_f3_algebra_shares_the_math_layout_and_evaluates_nested_selections(self):
        with tempfile.TemporaryDirectory() as folder:
            app = ConsoleApp(config_path=Path(folder) / "settings.json")
            math_algebra = next(item for item in app.menus[0]["items"] if item["key"] == "9")
            self.assertEqual(app.menus[2], {"label": "Algebra", "items": math_algebra["items"]})
            self.assertIsNot(app.menus[2]["items"], math_algebra["items"])
            for keys, token, arguments, expected in (
                (("1",), "solve(", "x^2=4,x)", "[-2, 2]"),
                (("9", "1"), "tExpand(", "sin(2*x))", "2*sin(x)*cos(x)"),
                (("TAB", "a", "1"), "cSolve(", "x^2+1=0,x)", "[-I, I]"),
                (("TAB", "b", "2"), "getDenom(", "1/x+1/2)", "2*x"),
            ):
                with self.subTest(token=token):
                    app.clear_input()
                    for key in ("F3", *keys):
                        app.handle_key(key)
                    self.assertEqual(app.text, token)
                    app.insert(arguments)
                    app.handle_key("ENTER")
                    self.assertEqual(app.calculator.history[-1].result, expected)

    def test_reference_paths_survive_configuration_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            app = ConsoleApp(config_path=Path(folder) / "settings.json")

            def check(reference, items, parent):
                self.assertEqual(len(reference), len(items))
                for entry, item in zip(reference, items):
                    path = [*parent, entry["key"]]
                    self.assertEqual(entry["path"], path)
                    self.assertEqual(item["key"], entry["key"])
                    if "items" in entry:
                        self.assertEqual(item["label"], entry["name"])
                        check(entry["items"], item["items"], path)
                    else:
                        token = entry["function"]
                        kind = math_item_kind(entry)
                        self.assertEqual(item["insert"].strip(), token)
                        if kind == "command":
                            self.assertIn(token, COMMANDS)
                        elif kind == "function":
                            self.assertIn(token.removesuffix("("), FUNCTIONS)
                        else:
                            operator = normalize_input(token).removesuffix("(")
                            self.assertIsNotNone(TOKEN.fullmatch(operator))

            check(MATH_MENU, validate_menus(app.menus)[0]["items"], [])
            for key in ("F1", "4", "TAB", "h", "2"):
                app.handle_key(key)
            self.assertEqual(app.text, "rowNorm(")
            app.insert("[[1, -3], [2, 1]])")
            app.handle_key("ENTER")
            self.assertEqual(app.calculator.answer.value, 4)
            app.save_config()
            reopened = ConsoleApp(config_path=app.config_path)
            self.assertEqual(reopened.menus[0], app.menus[0])


class MathEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def check(self, examples):
        for expression, expected in examples.items():
            with self.subTest(expression=expression):
                self.assertEqual(self.calc.calculate(expression), expected)

    def test_numbers_angles_and_trig(self):
        self.check({"exact(approx(2/3))": "2/3", "exact(approx(pi))": "pi",
                    "round([-2.345, 3.1415],2)": "[-47/20, 157/50]", "round(1.234)": "617/500",
                    "fPart(-8/3)": "-2/3", "remain(-5,3)": "-2", "mod(-5,3)": "1", "root(-8,3)": "-2",
                    "sin(90°)": "1", "sin(100ᵍ)": "1", "sin⁻¹(1)": "pi/2", "P▶Ry(2,30°)": "1",
                    "cosh⁻¹(1)": "0", "(pi/2)▶DD": "90°", "(pi/3)▶DMS": "60°0′0″", "2∠90°": "2*I",
                    "sin(60°0′0″)": "sqrt(3)/2",
                    "[[3,4]]▶Polar▶Rect": "[3, 4]", "conj(2+3*i)": "2 - 3*I"})
        self.calc.set_mode("degree")
        self.check({"sin((pi/2)ʳ)": "1", "sec(60)": "2", "cos⁻¹(0)": "90", "angle(i)": "90"})

    def test_lists_matrices_and_stateful_commands(self):
        self.check({"seq(x^2,x,1,3)": "[1, 4, 9]", "cumSum([[1,2],[3,4]])": "[[1, 2], [4, 6]]",
                    "sum([2,4,6],2)": "10", "min([3,1],[2,4])": "[2, 1]", "Δlist([5,9,3])": "[4, -6]",
                    "mat▶list(list▶mat([1,2,3],2))": "[1, 2, 3, 0]", "[[1,2],[3,4]]ᵀ": "[[1, 3], [2, 4]]",
                    "[[1,2],[3,4]] .* 2": "[[2, 4], [6, 8]]", "det([[1,2],[3,4]])": "-2",
                    "2.+[[1,2]]": "[[3, 4]]",
                    "rref([[2,2],[1,3]])": "[[1, 0], [0, 1]]", "rowAdd([[1,2],[3,4]],1,2)": "[[1, 2], [4, 6]]",
                    "[2,1]->numbers": "[2, 1]", '["b","a"]->letters': '["b", "a"]',
                    "SortA numbers,letters": "[1, 2]", "letters": '["a", "b"]',
                    "Fill 0,numbers": "[0, 0]", "Mat▶Data [[2,3],[4,5]],data,2,1": "[[4, 5]]",
                    "Data▶Mat data,output": "[[4, 5]]", "output": "[[4, 5]]"})
        self.calc.calculate("LU [[0,1],[2,3]],lower,upper,perm")
        self.check({"lower*upper": "[[2, 3], [0, 1]]", "perm*[[0,1],[2,3]]": "[[2, 3], [0, 1]]"})
        with self.assertRaises(CalcError):
            self.calc.calculate("LU [[1]],lower,lower,perm")
        self.check({"lower*upper": "[[2, 3], [0, 1]]"})

    def test_algebra_calculus_logic_and_strings(self):
        self.check({"solve(x^2=4,x)": "[-2, 2]", "solve([x+y=3,x-y=1],[x,y])": "[[2, 1]]",
                    "solve(x<3,x)": "x < 3",
                    "cZeros(x^2+1,x)": "[-I, I]", "left(x+1>=5)": "x + 1", "right(x+1>=5)": "5",
                    "d(x^3,x,2)": "6*x", "∫(x,x,0,2)": "2", "limit(sin(x)/x,x,0)": "1",
                    "Σ((1/2)^x,x,0,∞)": "2", "Π(x,x,1,4)": "24", "impDif(x^2+y^2=1,x,y)": "-x/y",
                    "deSolve(d(y(x),x)=y(x),x,y)": "C1*exp(x)", "1<2 and 3>=3": "True",
                    "deSolve(y'=y and y(0)=2,x,y)": "2*exp(x)",
                    "deSolve(y''=-y and y(0)=0 and y'(0)=1,x,y)": "sin(x)",
                    "True xor False": "True", "1<2 xor 3<4": "False", "1<2 xor False": "True",
                    "not True": "False", "7 and 5": "5", "7 xor 0 and 2": "7",
                    '"3->x" & "⇒0hAB-π"': '"3->x⇒0hAB-π"', 'expr("1+2")': "3",
                    'mid("abcdef",2,3)': '"bcd"', 'format(1/3,"F2")': '"0.33"',
                    'ord(char(65))': "65", "(15+1)▶Hex": "0h10", "0h10▶Bin": "0b10000", "ans+1": "17",
                    "rotate(0h80000000,1)": "1"})

    def test_statistics_regression_and_probability(self):
        self.check({"mean([1,2,3],[1,0,3])": "5/2", "median([1,4,10,13])": "7",
                    "variance([1,2,3])": "1", "nCr(5,2)": "10", "nPr(5,2)": "20", "isPrime(101)": "True"})
        calculated = self.calc.calculate("LinReg [1,2,3],[3,5,7]")
        self.assertIn("regEq = 2*x + 1", calculated)
        self.assertEqual(self.calc.calculate("ShowStat"), calculated)
        self.assertEqual(self.calc.evaluate("statA").value, sp.Integer(2))
        self.calc.calculate("PowerReg [1,2,3],[2,8,18]")
        power_model = self.calc.evaluate("statRegEq").value
        self.assertAlmostEqual(float(power_model.subs("x", 4)), 32)
        self.calc.calculate("RandSeed 13")
        before = self.calc.calculate("randMat(2,2)")
        self.calc.calculate("RandSeed 13")
        self.assertEqual(self.calc.calculate("randMat(2,2)"), before)
        self.check({"rand(-1)": "-1", "rand(1)": "1"})
