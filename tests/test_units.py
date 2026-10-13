import unittest

import sympy as sp

from calc_term import CalcError, Calculator, Quantity, dimension


REQUESTED_UNITS = """
c Cc g Gc h k Me Mn Mp Na q Rb Rc Rdb Vm ε0 σ φ0 μ0 μb
Ang au cm fath fm ft in km ltyr m mi mil mm Nmi pc rod yd μ Å acre ha
cup floz flozUK gal galUK l ml pt qt tbsp tsp day hr min ms ns s week yr μs
knot kph mph °C °F °K °R cd mol amu gm kg lb mg mton oz slug ton tonne tonUK
dyne kgf lbf N tonf Btu cal erg eV ftlb J kcal kWh latm hp kW W
atm bar inH2O inHg mmH2O mmHg Pa psi torr St P GHz Hz kHz MHz A kA mA μA
coul kV mV V volt kΩ MΩ ohm Ω mho mmho siemens μmho F nF pF μF
Oe Gs T Wb henry mH nH μH
""".split()


class UnitTests(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_every_requested_unit_exists_and_ignores_case(self):
        for name in REQUESTED_UNITS:
            with self.subTest(name=name):
                unit = self.calc.registry.get("_" + name)
                self.assertIs(unit, self.calc.registry.get("_" + name.swapcase()))
                self.assertFalse(unit.scale.atoms(sp.Float))

    def test_micro_sign_alias(self):
        self.assertEqual(self.calc.calculate("1_µs=>_ns"), "1000_ns")
        self.assertEqual(self.calc.calculate("1_ΜS=>_ns"), "1000_ns")

    def test_inch_to_foot_and_fraction_input(self):
        self.assertEqual(self.calc.calculate("3_in=>_ft"), "1/4_ft")
        self.assertEqual(self.calc.calculate("1/4_ft=>_in"), "3_in")
        self.assertEqual(self.calc.calculate("3_IN=>_FT"), "1/4_ft")

    def test_digit_separators_do_not_change_unit_suffixes(self):
        self.assertEqual(self.calc.calculate("1_000_m=>_km"), "1_km")
        self.assertEqual(self.calc.history[-1].line, "1000_m=>_km = 1_km")
        self.assertEqual(self.calc.calculate("3_000_in=>_ft"), "250_ft")
        self.assertEqual(self.calc.calculate("1/1_000_ft=>_ft"), "1/1000_ft")
        self.assertEqual(self.calc.calculate("1_000/4_ft=>_ft"), "250_ft")
        self.calc.evaluate("1_000_ε0")
        self.assertEqual(self.calc.history[-1].source, "1000_ε0")
        self.calc.define_unit("span", "1_000_m")
        self.assertEqual(self.calc.calculate("1_span=>_km"), "1_km")

    def test_base_literals_work_with_unit_suffixes_and_custom_units(self):
        self.assertEqual(self.calc.calculate("0hC_ft=>_in"), "144_in")
        self.assertEqual(self.calc.history[-1].source, "12_ft=>_in")
        self.assertEqual(self.calc.calculate("0b10_km=>_m"), "2000_m")
        self.assertEqual(self.calc.calculate("0o10_m"), "8_m")
        self.assertEqual(self.calc.calculate("0h3/0hC_ft=>_in"), "3_in")
        self.calc.define_unit("span", "0o10_m")
        self.assertEqual(self.calc.calculate("0b10_span=>_m"), "16_m")
        self.calc.define_unit("unit0hFF", "1_m")
        self.assertEqual(self.calc.calculate("0b10_unit0hFF=>_m"), "2_m")

    def test_known_unit_suffixes_take_precedence_over_hex_separator_groups(self):
        self.assertEqual(self.calc.calculate("0hC_F"), "12_F")
        self.assertEqual(self.calc.calculate("0hC_cd"), "12_cd")

    def test_catalog_conversion_examples(self):
        conversions = {
            "1_mi=>_ft": "5280", "1_Nmi=>_m": "1852", "1_Ang=>_Å": "1",
            "1_au=>_m": "149597870700", "1_ltyr=>_m": "9460730472580800",
            "1_acre=>_ft^2": "43560", "1_ha=>_m^2": "10000",
            "1_gal=>_in^3": "231", "1_galUK=>_l": "4.54609", "1_cup=>_floz": "8",
            "1_tbsp=>_tsp": "3", "1_week=>_hr": "168", "1_yr=>_day": "365.25",
            "1_mph=>_kph": "1.609344", "1_knot=>_kph": "1.852",
            "1_lb=>_oz": "16", "1_tonUK=>_lb": "2240", "1_ton=>_lb": "2000",
            "1_tonne=>_kg": "1000", "1_kgf=>_N": "9.80665", "1_dyne=>_N": "1e-5",
            "1_cal=>_J": "4.184", "1_kWh=>_J": "3600000", "1_latm=>_J": "101.325",
            "1_hp=>_W": "745.69987158227022", "1_atm=>_torr": "760",
            "1_bar=>_Pa": "100000", "1_St=>_m^2/_s": "1e-4", "1_P=>_Pa*_s": "0.1",
            "1_GHz=>_Hz": "1e9", "1_kA=>_A": "1000", "1_mA=>_μA": "1000",
            "1_kV=>_volt": "1000", "1_MΩ=>_kΩ": "1000", "1_mmho=>_siemens": "0.001",
            "1_μF=>_nF": "1000", "1_Gs=>_T": "1e-4", "1_mH=>_μH": "1000",
        }
        for source, expected in conversions.items():
            with self.subTest(source=source):
                quantity = self.calc.evaluate(source)
                unit = quantity.display
                magnitude = sp.simplify((quantity.value - unit.offset) / unit.scale)
                self.assertEqual(magnitude, sp.Rational(expected))

    def test_temperature_conversions(self):
        samples = {"32_°F=>_°C": "0_°C", "100_°C=>_°F": "212_°F",
                   "0_°C=>_°K": "5463/20_°K", "-40_°C=>_°F": "-40_°F",
                   "-40_°F=>_°C": "-40_°C", "-273.15_°C=>_°K": "0_°K",
                   "491.67_°R=>_°C": "0_°C", "18_deltaF=>_deltaC": "10_deltaC"}
        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(self.calc.calculate(source), expected)
        self.assertEqual(self.calc.calculate("100_°C-0_°C"), "100_deltaK")

    def test_dimension_arithmetic_and_assignment(self):
        self.calc.evaluate("3_ft->x")
        self.assertEqual(self.calc.calculate("4*x=>_in"), "144_in")
        self.assertEqual(self.calc.calculate("1_m+20_cm"), "6/5_m")
        self.assertEqual(self.calc.calculate("(1_kg*2_m/_s^2)=>_N"), "2_N")
        self.assertEqual(self.calc.calculate("(2_N*3_m)=>_J"), "6_J")
        self.assertEqual(self.calc.calculate("(1_V*1_A)=>_W"), "1_W")
        self.assertEqual(self.calc.calculate("(1_coul/1_s)=>_A"), "1_A")

    def test_area_suffix_does_not_square_coefficient(self):
        value = self.calc.evaluate("2_m^2=>_cm^2")
        self.assertEqual(value.value / value.display.scale, 20000)
        self.assertEqual(self.calc.calculate("sqrt(9_cm^2)=>_cm"), "3_cm")

    def test_unit_mismatch_and_invalid_units(self):
        for source in ["1_m+1_s", "1_m=>_s", "1_unknown", "sin(1_m)", "1_m^x",
                       "1_m^1_s", "2_°C*3", "1_m=>_°C/_s", "1_m=>_c",
                       "1_m=>", "1_m=>_m=>_ft", "1_m=>-_m", "1_m_s"]:
            with self.subTest(source=source), self.assertRaises(CalcError):
                self.calc.evaluate(source)

    def test_physical_constants(self):
        self.assertEqual(self.calc.evaluate("_c").value, 299792458)
        self.assertEqual(self.calc.evaluate("_c").dims, dimension(L=1, T=-1))
        self.assertEqual(self.calc.evaluate("_g").value, sp.Rational("9.80665"))
        self.assertEqual(self.calc.evaluate("_Me").value, sp.Rational("9.1093837139e-31"))
        self.assertEqual(self.calc.evaluate("_φ0").value, sp.Mul(sp.Rational("6.62607015e-34"), sp.Pow(sp.Mul(2, sp.Rational("1.602176634e-19")), -1)))
        self.assertEqual(self.calc.evaluate("_Rc").value, sp.Rational("8.31446261815324"))
        self.assertEqual(self.calc.evaluate("_Vm").value, self.calc.evaluate("_Rc").value * sp.Rational("273.15") / 101325)
        self.assertEqual(self.calc.calculate("(_c*1_s)=>_m"), "299792458_m")
        self.assertEqual(self.calc.calculate("_Na*1_mol"), "602214076000000000000000")

    def test_user_defined_units(self):
        self.calc.define_unit("smoot", "1.7018_m")
        self.calc.define_unit("doubleSmoot", "2_smoot")
        self.assertEqual(self.calc.calculate("1_SMOOT=>_cm"), "8509/50_cm")
        self.assertEqual(self.calc.calculate("2_smoot=>_doubleSmoot"), "1_doubleSmoot")
        self.calc.define_unit("speed", "1_m/_s")
        self.assertEqual(self.calc.calculate("10_speed=>_kph"), "36_kph")

    def test_custom_unit_snapshots_assigned_scale(self):
        self.calc.evaluate("2_m->x")
        self.calc.define_unit("span", "3*x")
        self.calc.evaluate("99->x")
        restored = Calculator()
        restored.define_unit("span", self.calc.unit_definitions["span"])
        self.assertEqual(restored.calculate("1_span=>_m"), "6_m")

    def test_invalid_custom_units(self):
        for name, definition in [("FT", "1_m"), ("bad", "-1_m"), ("zero", "0_m"),
                                 ("offset", "1_°C"), ("sym", "x_m"), ("1bad", "1_m"),
                                 ("bad_name", "1_m"), ("inf", "1/0")]:
            with self.subTest(name=name), self.assertRaises(CalcError):
                self.calc.define_unit(name, definition)

    def test_results_can_be_reparsed_without_losing_dimensions(self):
        sources = ["3_in=>_ft", "1_m/3_s", "sqrt(2)_ft", "2_m^2", "sqrt(9_cm^2)",
                   "1_m^(-1/2)", "(y+1)_m", "_c", "_σ", "_μ0", "1_Oe", "-40_°C",
                   "3_m/_s=>_km/_hr", "1_m^2/_s", "1/3_°F", "1_kg*2_m/_s^2"]
        for source in sources:
            with self.subTest(source=source):
                first = self.calc.evaluate(source)
                formatted = self.calc.registry.format(first)
                second = self.calc.parse(formatted)
                self.assertEqual(second.dims, first.dims, formatted)
                self.assertEqual(sp.simplify(second.value - first.value), 0, formatted)


if __name__ == "__main__":
    unittest.main()
