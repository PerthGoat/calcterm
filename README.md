# Console calculator

`calc_term.py` is a Python terminal application with six configurable dropdown menus,
a history panel that fills the terminal, an editable input line, and a status bar. It runs on
Windows, macOS, and Linux. Python 3.10 or newer and SymPy are required; SymPy is the
only direct external dependency (it installs mpmath for arbitrary-precision evaluation).

Install and run from this directory:

```powershell
python -m pip install -r requirements.txt
python calc_term.py
```

If using this project's existing Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe calc_term.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The interactive UI needs a terminal that supports ANSI output. Windows Terminal and
modern Windows console hosts support it. Use `--plain` in a basic terminal or pipe;
redirected input/output selects plain mode automatically. Quit using `:quit`, Ctrl+C,
or Ctrl+D. The interactive app restores the terminal when it exits.

## Keyboard

| Key | Action |
| --- | --- |
| F1–F6 | Open/close Math, Units, Constants, Symbols, Options, and Help menus |
| Up / Down | Select history results and expressions while preserving the input cursor |
| Enter with history selected | Insert the highlighted part at the input cursor |
| Enter in input | Calculate the expression or execute a `:` command |
| Left / Right | Move the input cursor; open/return from submenus or switch top menus |
| Home / End | Move to the input ends or the first/last dropdown item |
| Backspace / Delete | Edit the input |
| PageUp / PageDown | Browse history or page through a dropdown |
| Tab | Switch input/history focus |
| Esc | Return to input or close a menu/help |
| Ctrl+U | Clear the input |
| Ctrl+L | Redraw |

In a dropdown, use Up/Down and Enter to choose an item. Type to filter its labels;
Backspace edits the filter. In F2, choose a unit category with Enter or Right, then
choose its unit with Enter. Left or Esc returns to the category list; Esc again
closes it. Filtering the category list also searches the units inside each category.
Right on a unit switches to F3 Constants, clearing the submenu and filter; this
also works when the submenu filter has no matches. In any menu, Right opens a
selected submenu when available, or otherwise switches to the next top menu.
Submenus appear beside their parent when space permits, or over it in narrow terminals.
F4 includes ε, μ, Ω, π, other Greek letters, °, Å, and
arrows. Selection inserts the symbol at the input cursor. Terminal size must be at
least 40 columns by 12 rows.

The history limit is **at least 30 calculations, including errors**, increasing to the
number of visible history rows in taller terminals. The panel fills the space
between the menu and input line. Resizing the terminal updates the panel immediately,
with the input, status, and message bars at the bottom. The status bar shows the
current limit. Shrinking the terminal keeps the latest entries up to the new limit.
Selecting an older entry scrolls the visible history. Failed calculations appear as
`1/0 = Error: Division by zero.` and keep the input for correction. Errors leave
assignments and `ans` intact. Only the expression is selectable in error entries,
so Enter recalls the bad input for editing. Up first highlights the newest
result, then its expression, then the previous result and expression, continuing
through history. For `5+3 = 8`, the first Up selects `8` and the second selects `5+3`.
Down reverses this order and returns to input after the newest result. Only the
selected part is highlighted, and Enter inserts that part. Selected results after
long expressions scroll into view. PageUp/PageDown jump one visible page of entries at a time.
`:recall expression` changes the initial selection to the expression; both parts
remain selectable with Up/Down. Composite recalled
results are enclosed in parentheses to preserve arithmetic precedence.

History saves automatically after each calculation, including errors, and restores on startup,
including in `--plain` and `--eval` modes. It is stored separately from settings in
`calc_term_config.history.json` beside the script; `--config my_settings.json` uses
`my_settings.history.json` beside that settings file. No `:save` is needed for history.
`:clear` also clears saved history. The history limit still follows the terminal height,
with a minimum of 30. Restoring history displays the recorded expressions and results
without evaluating them again. Variables last for the current session; `:save` saves
settings, units, and menus.

## Math

```text
3->x                    = 3
4*x                     = 12
7->X                    = 7
x+X                     = 10
0.1+0.2                 = 3/10
1/3+1/6                 = 1/2
3>6                     = False
3<=6                    = True
0.1+0.2==0.3            = True
3!=6                    = True
3_in=>_ft               = 1/4_ft
1/4_ft=>_in             = 3_in
3_m/_s=>_kph            = 54/5_kph
32_°F=>_°C              = 0_°C
expand((y+1)^2)         = y^2 + 2*y + 1
diff(y^3,y)             = 3*y^2
integrate(y^2,y,0,3)    = 9
solve(y^2-4,y)          = [-2, 2]
subs(y^2+1,y,3)         = 10
```

`->` assigns a value to a variable; `=>` converts units. Their Unicode equivalents
`→` and `⇒` also work. Letters and Unicode variable names are case-sensitive; unit
names are case-insensitive, including Greek letters. `_µs` and `_μs` are equivalent.
Use `_gm` for grams, `_hr` for hours, and `_°K` for Kelvin; `_g`, `_h`, and `_k`
are physical constants. The built-in names `pi`/`π`, `e`/`E`, `i`/`I`, `ans`, and
function names are reserved. `ans` holds the latest successful result in the current
session: after `2+3`, `ans*4` gives `20`, then `ans+1` gives `21`. Failed input and
`:clear` leave `ans` unchanged. It starts at `0` when the app opens.

Unassigned variables stay symbolic. Assignments use the values available when the
expression is entered; they are not reactive formulas. Use `:unset x` to make an
assigned name symbolic again before differentiating or solving with that variable.

Supported operators are `+ - * / ^ ** % !`, parentheses, and implicit multiplication
such as `2(x+1)`. `^` is exponentiation and associates to the right; `-2^2` is `-4`.
Comparisons `<`, `>`, `<=`, `>=`, `=` (or `==`), and `!=` return `True` or `False`.
The Unicode forms `≤`, `≥`, and `≠` also work. Arithmetic takes precedence over
comparisons, and chains such as `1<2<=3` compare each adjacent pair. Compatible
units are compared in their base units: `1_m==100_cm` returns `True`; comparing
different dimensions is an error. Assign numeric values to symbolic variables
before comparing them if the result cannot otherwise be determined.
Boolean results work with assignments, `ans`, and history recall; `True` and `False`
are reserved literals. Booleans support equality comparisons and cannot be used
in arithmetic, unit conversions, or scalar functions.

Bitwise operators work on dimensionless exact integers:

| Operator | Meaning | Example |
| --- | --- | --- |
| `&` | AND | `5&3 = 1` |
| `\|` | OR | `5\|3 = 7` |
| `xor` | Exclusive OR | `5 xor 3 = 6` |
| `~` | NOT | `~5 = -6` |
| `<<` | Shift left | `5<<2 = 20` |
| `>>` | Shift right | `20>>2 = 5` |

`^` remains exponentiation; use the lowercase word `xor` for exclusive OR. `xor` is
reserved and cannot be assigned a value. Binary, octal, and hexadecimal inputs work:
`0hFF & 0b1010` gives `10`. Results use decimal notation and support assignments,
`ans`, and history recall. Integers have arbitrary width; negative values behave
as signed integers with sign extension, so `~0` is `-1` and `-5>>1` is `-3`.
Shift counts must be nonnegative. Fractions, units, booleans, symbolic values,
and explicit floating-point approximations are rejected as bitwise operands.

From higher to lower precedence: powers, unary `+ - ~`, multiplication/division,
addition/subtraction, shifts, `&`, `xor`, `|`, then comparisons. Factorial and unit
suffixes bind most tightly. For example, `1<<1+2` is `8`, and `5&3==1` is `True`.
Use parentheses to override precedence.

Functions include `sqrt`, `cbrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `sinh`,
`cosh`, `tanh`, `exp`, `ln`, `log`, `abs`, `floor`, `ceil`, `factorial`, `min`, `max`,
`simplify`, `expand`, `factor`, `diff`, `integrate`, `solve`, `subs`, and `approx`.
`log(x)` is base 10; `ln(x)` is natural log; `log(x,b)` sets another base.
Inverse trig results follow the selected angle mode; hyperbolic functions do not.
`diff(expression,variable,order)` supports higher derivatives.

Decimal and scientific-notation inputs become **exact rational numbers**, and
integers have arbitrary length. Use underscores between digits as grouping separators:
`1_000 + 2_500` evaluates to `3500` and appears in history as `1000 + 2500 = 3500`.
History removes numeric separators while preserving unit suffixes, so
`1_000_m=>_km` appears as `1000_m=>_km = 1_km`. Grouping also works in fractions,
decimal numbers, and exponents; leading, trailing, and repeated separators are invalid.
Enter binary integers with `0b`, hexadecimal integers with `0h`, and octal integers
with `0o`. They convert to decimal on submission, including in history and recalled
expressions: `0h3FA2` becomes `16290`, `0b1010` becomes `10`, and `0o17` becomes `15`.
Prefixes and hexadecimal letters can use either case. Negative values, digit separators
(`0hDEAD_BEEF`), arithmetic, assignments, and unit suffixes all work. Known unit suffixes
retain their meaning: `0hC_F` means `12_F`; use `0hCF` for the integer `207`.
Invalid digits and non-integer base literals are rejected.
Exact output is the default: fractions and irrational values remain symbolic, such as
`1/3`, `sqrt(2)`, and `pi`. F5 Options offers **Exact output** and **Approximate output**.
You can also use `:format exact` or `:format approximate` (`:format approx` works too).
`:precision 12` makes approximate output show up to 12 significant decimal digits:
`1/3` displays as `0.333333333333`, and `3_in=>_ft` as `0.25_ft`. Integers remain intact.
The status bar shows the current output mode. Use `:save` to keep the preference.

Automatic approximation affects displayed results, including new history entries;
calculations, variables, and `ans` retain their exact values. Switching modes leaves
existing history entries unchanged. Symbolic expressions and solution lists are
supported, and conversions are performed before rounding the result.

`approx(pi,100)` explicitly requests an approximation with 100 significant decimal
digits, overriding the default output precision for that value. `:precision 100`
also sets the default for `approx(expression)`. Explicit approximations are finite-precision
values, so subsequent arithmetic on those values follows their precision.
The implementation follows [SymPy's exact arithmetic and arbitrary-precision model](https://docs.sympy.org/latest/tutorial/basic_operations.html).

## Units and constants

Every unit and constant requested is included, across length, area, volume, time,
velocity, temperature, mass, force, energy, power, pressure, viscosity, frequency,
current, charge, potential, resistance, conductance, capacitance, magnetic fields,
flux, inductance, luminous intensity, and amount of substance. F2 lists units by
category, each opening a submenu of its units; F3 lists constants. User-defined
units appear in the Custom submenu. `_mps2` supplies acceleration, and compound units work:

```text
2_m^2=>_cm^2
1_kg*2_m/_s^2=>_N
1_St=>_m^2/_s
_c*1_s=>_m
```

`2_m^2` means **2 square meters**, while `(2_m)^2` means **4 square meters**.
Fractional unit exponents require parentheses: `_m^(1/2)`. A suffix applies a unit
to a scalar; use `*` and `/` to combine quantities and units. Contiguous fraction
literals such as `1/4_ft` mean one quarter of a foot, while `1/(4_ft)` means the
inverse of four feet. Output keeps exact fractions and can be entered again.

Conversions check physical dimensions. Offset temperature conversions are supported
for `_°C` and `_°F`; use `_°K` for compound units or products involving absolute
temperatures, and `_deltaC`, `_deltaF`, or `_deltaK` for temperature differences.
Subtracting two Celsius/Fahrenheit absolute temperatures produces a Kelvin difference.

Volumes without `UK` use US customary definitions. `_cal`/`_kcal` use thermochemical
calories, `_Btu` uses the international-table Btu, and `_hp` is mechanical horsepower.
Water/mercury pressure columns use conventional standard-gravity factors. `_yr` is
a Julian year of 365.25 days; `_ltyr` uses that year. A parsec is exactly
`648000/pi` astronomical units.

Physical constants use the [NIST CODATA 2022 table](https://physics.nist.gov/cuu/Constants/Table/allascii.txt).
Defined constants retain exact values; measured constants use the published central
values and cannot acquire additional physical accuracy from additional numerical
precision. `_Cc` is derived from the tabulated permittivity, `_Rc` from `_Na*_k`,
`_σ` from its exact symbolic definition, and `_φ0` from `_h/(2*_q)`.
`_Vm` is for **273.15 K at 1 atmosphere**, rather than 1 bar. Measurement uncertainties
are not propagated.

Add a user-defined unit using a positive numeric quantity:

```text
:unit smoot = 1.7018_m
:unit doubleSmoot = 2_smoot
1_smoot=>_cm
:save
```

Custom units can use compound dimensions and previously defined units. Built-in
names cannot be overwritten. Saved definitions store their evaluated scale so they
do not depend on session variables. Custom offset temperature units are not supported.

## Configure menus

Change labels and items in the app, then save:

```text
:menu 1 Favorites
:menuclear 1
:menuadd 1 Square | ^2
:menuadd 1 Epsilon | ε
:menuadd 1 Degrees | :mode degree
:save
```

A menu item runs a `:` command if its text begins with `:`; otherwise it inserts
text at the cursor. Each of the six menus can be configured. Options contains
commands for radians/degrees, exact/approximate output, recall behavior, precision,
menu editing, and saving.
The settings file defaults to `calc_term_config.json` beside the script. Choose
another with `python calc_term.py --config my_settings.json`. Changes persist when
you execute `:save` or select Save configuration in F5.

You can also edit the JSON file. It needs exactly six menus; each item needs a label
and exactly one of `insert`, `command`, or an `items` list for a submenu. Submenus
can nest up to eight levels. Older flat F2 unit lists are grouped by category when
loaded, preserving other actions. For example:

```json
{
  "mode": "radian",
  "precision": 100,
  "output_mode": "exact",
  "history_insert": "result",
  "units": {"smoot": "1.7018_m"},
  "menus": [
    {"label": "Favorites", "items": [{"label": "Square", "insert": "^2"}]},
    {"label": "Units", "items": [{"label": "Length", "items": [{"label": "Feet", "insert": "_ft"}]}]},
    {"label": "Constants", "items": [{"label": "Light speed", "insert": "_c"}]},
    {"label": "Symbols", "items": [{"label": "Epsilon", "insert": "ε"}]},
    {"label": "Options", "items": [{"label": "Degrees", "command": ":mode degree"}]},
    {"label": "Help", "items": [{"label": "Keyboard", "command": ":help"}]}
  ]
}
```

Omit `menus` to retain the built-in menus while configuring units or settings.
Invalid configurations show an error, use defaults, and preserve the original file.
Neither math input nor configuration executes Python or shell code.

Other commands are `:vars`, `:unset NAME`, `:clear` (history), `:recall result`,
`:recall expression`, `:mode radian`, `:mode degree`, `:format exact`,
`:format approximate`, `:precision DIGITS`, `:help`,
and `:quit`.

For scripting, `--eval` can be repeated; expressions share variables and return a
nonzero exit code on errors:

```powershell
python calc_term.py --eval "3->x" --eval "4*x" --eval "3_in=>_ft"
python -m unittest discover -s tests -v
```
