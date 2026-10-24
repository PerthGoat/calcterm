# Console calculator

`calc_term.py` is a Python terminal application with six configurable dropdown menus,
a y1–y99 equation editor, a history panel that fills the terminal, an editable input line,
and a status bar. It runs on
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

Expressions use terminal syntax colors: **dark amber numbers**, **cyan function names**,
**green units/physical constants**, **magenta built-in values** (such as `pi` and `ans`),
and **blue operators/commands**. Colors appear as you type, including incomplete
expressions, and in history, the equation editor, and table values. Selected text
uses inverse highlighting for readability. Input, saved history, and plain/batch
output remain ordinary text.

Colors are **on by default**. In **F5 Options**, select **Syntax colors: On/Off** to
toggle them immediately. Text selection remains highlighted when colors are off.
The preference saves automatically and is restored when the app reopens.
The setting is shared across Problems. Commands `:colors on`, `:colors off`, and
`:colors toggle` also work; JSON settings use `"syntax_colors": true` or `false`.

## Keyboard

| Key | Action |
| --- | --- |
| F1–F6 | Open/close Math, Units, Constants, Symbols, Options, and Help menus |
| F7 | Open the equation editor, or save the current equation and close it |
| F8 | Open/close the table of checked equations |
| F9 | Open/close Clean Up: clear variables/history or reset configuration |
| Ctrl+T in F7 | Check/uncheck the selected equation for the table |
| Up / Down | Select history results and expressions while preserving the input cursor |
| Enter with history selected | Insert the highlighted part at the input cursor |
| Backspace with history selected | Delete the whole selected history entry |
| Enter in input | Calculate and select the expression, or execute a `:` command |
| Shift+Enter in input | Calculate an approximate result for this submission |
| Left / Right | Move the input cursor; open/return from submenus or switch top menus |
| Shift+Left / Shift+Right | Extend or shrink the input selection |
| Insert | Toggle overwrite typing; show/hide INS in the status bar |
| Home / End | Move to the input ends or the first/last dropdown item |
| Backspace / Delete | Edit the input |
| PageUp / PageDown | Browse history or page through a dropdown |
| Tab | Switch input/history focus |
| Esc | Return to input or close a menu/help |
| Ctrl+U | Clear the input |
| Ctrl+L | Redraw |

After a calculation, the expression stays in the input bar with all its text selected.
Backspace or Delete clears the selected expression; typing replaces it. Left moves the
cursor to its beginning, and Right moves it to its end, clearing the selection so you
can edit normally. Home/End also clears the selection and moves to the corresponding
end. Enter again recalculates the expression. History, menu, and Catalog insertions
replace selected input. Failed calculations use the same selection behavior; `:` commands
continue to clear the input after successful execution.

**Shift+Enter** displays this calculation's result approximately at the configured
precision, in either exact or approximate mode. It leaves the output mode unchanged;
ordinary Enter continues to follow that setting. The approximate display is saved in
history, while `ans` and assignments retain their underlying exact values.

On Windows, the app detects Shift with Enter directly. On macOS/Linux it accepts
CSI-u and [xterm modified-key reports](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html#h2-Key-Modifiers)
and requests modified-key reporting while running. The terminal must distinguish
Shift+Enter from ordinary Enter for the shortcut to work.

Hold **Shift** while pressing Left or Right to select part of the input. Reversing
direction shrinks the selection; continuing past its starting point selects in the
opposite direction. Typing, history recall, and menu/Catalog insertions replace only
the selected portion, while Backspace/Delete removes it. Plain Left/Right collapses
a partial selection to its left/right edge.

**Insert** toggles insertion mode with overwrite typing: when **INS** is shown, typed
characters replace existing characters at the cursor. Typing at the end appends text.
Selected text is replaced as a unit. The mode also applies to the equation editor,
table setup, and new Problem name field. Menu, Catalog, and history insertions keep
their insertion behavior. The mode starts off when the app opens.

The bottom status bar has fixed slots: `ProblemName | ↑ | INS | RADIAN`. The INS slot
stays blank when insertion mode is off. On Windows, the arrow appears while Shift is
physically held and its slot stays blank when released, keeping the layout stable.
It updates even without another key
press and is also shown in the equation editor and table. Other platforms keep it
hidden because ordinary terminal input does not reliably report bare Shift releases.

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

**F9 Clean Up** contains **Clear set variables**, which makes assigned names symbolic
again, and **Clear history**, which clears the current Problem's saved history.
Both actions preserve equations and `ans`. Clear history has moved out of Options;
older saved Options menus are updated when loaded. F9 is a built-in menu; the six
F1–F6 menus keep their existing configuration format.

The third item, **Reset configuration**, restores radians, exact output, 50-digit
precision, result-first history recall, syntax colors on, insertion mode off, and
the default menus.
The reset saves automatically. Saved Problems, equations, history, table settings,
session variables/`ans`, and custom unit definitions are retained. The command
`:resetconfig` performs the same reset.

**F6 Help → Catalog** opens a large, centered popup with an alphabetical list of
every built-in function, y1–y99 equation slots, symbols, operators, built-in values,
physical constants, and units (including custom units). Custom single-character
symbols added to menus also appear. Function entries show their argument forms.
Type to filter by name or notation; Backspace edits the filter and Ctrl+U clears it.
Use Up/Down, PageUp/PageDown, or Home/End to browse. Enter inserts the selection at
the calculator cursor, using `name(` for a function. Esc closes the Catalog and keeps
your input untouched. Catalog is also available through the interactive `:catalog` command.

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
including in `--plain` and `--eval` modes. Each Problem stores its own history in the
Problems file described below. Existing history files are imported into Default;
`calc_term_config.history.json` is also maintained as a copy of Default's history.
No `:save` is needed for history. `:clear` clears the current Problem's saved history.
The history limit still follows the terminal height,
with a minimum of 30. Restoring history displays the recorded expressions and results
without evaluating them again. Variables last for the current session. General
settings, custom units, and menus save automatically when changed.

With a history entry selected, **Backspace deletes the entire calculation**, whether
its expression or result is highlighted. The deletion saves automatically in the
current Problem. Selection moves to the nearest remaining entry; deleting the last
one returns focus to input. The input, assigned variables, equations, and `ans` remain
available; removing history does not undo the calculation.

## Problems

**F5 Options → Problems** contains:

- **New Problem**: enter a name and press Enter to create an empty Problem.
- **Open Problem**: select a saved Problem and press Enter to open it. Type to filter names.
- **Delete Problem**: select a Problem, then confirm in the popup. **Cancel** is selected
  by default; use Left/Right or Tab to select **Delete**, then press Enter. Esc cancels.

Each Problem remembers its history, equations, equation checkmarks, and table start/step
settings automatically. The current Problem saves before you switch, and the app reopens
the last active Problem on startup. The calculator shows the current name at the bottom
left of the status bar, before the angle mode.
Names can contain spaces and Unicode, up to 80 printable characters; duplicates ignore case.

Existing work belongs to **Default**, which remains available and cannot be deleted.
Deleting the active named Problem returns to Default. General preferences, menus, and
custom units are shared between Problems. Assigned variables and `ans` are session values;
opening a Problem starts them fresh while restoring its recorded history without replaying it.

Problems are stored separately from general settings in `calc_term_config.problems.json`
beside the script. `--config my_settings.json` uses `my_settings.problems.json` instead.
Writes replace the file atomically; load/write errors are displayed and damaged files are
preserved. Back up the Problems file to keep all your saved work.

In plain mode, use `:problem new NAME` and `:problem open NAME`. The interactive
`:problem delete [NAME]` command opens the confirmation popup.

## Equations

Press **F7** to open the scrollable list of **y1 through y99**. Select a row with
Up/Down or PageUp/PageDown and enter its formula in terms of `x` on the entry line.
For example, type `4x` in the first slot; the entry line displays `y1(x)=4x`.
The list shows `[✓] y1=4x`, keeping `(x)` in the entry line only. New and changed
formulas are checked automatically. **Ctrl+T** checks/unchecks the selected formula
for the table; browsing or reopening an unchanged formula preserves its checkmark.
Press F7 again to save the formula and return to the calculator. Then:

```text
y1(3)       = 12
y1(1/3)     = 4/3
y1(2+1)+5   = 17
```

Enter saves and selects the next equation. Moving between rows also saves the
current formula. Left/Right, Home/End, Backspace, and Delete edit the formula;
Ctrl+U clears it, and saving an empty formula removes that definition. Esc discards
the current row's pending edit and closes the editor; previously saved rows remain.
Invalid formulas stay in the editor for correction. Your calculator input and cursor
are preserved while the editor is open.

Equations accept one dimensionless scalar argument, including symbolic expressions.
Their local `x` is independent of a calculator variable named `x`. Normal math functions,
exact arithmetic, and the selected angle/output modes work inside equations. Formulas
can call other slots, such as `y2(x)=y1(x)+x^2`; calls use their current definitions.
Other variables and `ans` also use their values at call time. Undefined slots and
circular references report errors when called. The names `y1` through `y99` are
reserved for equation calls and cannot be assigned ordinary variable values.

Equations save automatically when you save a row or leave the editor; **`:save` is
not required**. A valid formula still being edited also saves when the app exits
normally. Invalid pending edits leave the last valid formula intact, and Esc still
discards the current edit. Definitions from older settings files are imported into
Default when no Problems file exists. Saved equations can also be called in `--plain`
and `--eval` modes.

## Table

Press **F8** from the calculator or equation editor to display a table with an `x`
column and a column for each checked equation, in y1–y99 order. For example, with
`y1=4x` and `y2=x^2` checked:

```text
x          | y1         | y2
0          | 0          | 0
1          | 4          | 1
2          | 8          | 4
3          | 12         | 9
```

Press **Tab** to set the starting x value and step. Tab switches between the two
fields, Ctrl+U clears the current field, and Enter applies both values. The defaults
are start `0` and step `1`. Numeric expressions such as `1/3` or `pi/2` work; the
step can be negative but cannot be zero. Esc cancels a pending setup edit.

Up/Down scrolls one row; PageUp/PageDown scrolls a page. Left/Right reveals additional
equation columns when they do not all fit. Home returns to the starting x and first
equation column. F7 returns to equations; F8 or Esc closes the table. A calculation
that fails at a particular x displays `Error` in that cell while the other cells
remain available. Table calculations preserve calculator variables, `ans`, history,
and pending input. Unchecked equations can still be called normally in calculations.

Table settings and equation checkmarks save automatically in the current Problem.
Older settings default to checking all defined equations.

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
The status bar shows the current output mode. Preference changes save automatically.

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
```

Custom units can use compound dimensions and previously defined units. Built-in
names cannot be overwritten. Saved definitions store their evaluated scale so they
do not depend on session variables. Custom offset temperature units are not supported.

## Configure menus

Change labels and items in the app; each change saves automatically:

```text
:menu 1 Favorites
:menuclear 1
:menuadd 1 Square | ^2
:menuadd 1 Epsilon | ε
:menuadd 1 Degrees | :mode degree
```

A menu item runs a `:` command if its text begins with `:`; otherwise it inserts
text at the cursor. Each of the six menus can be configured. Options contains
commands for radians/degrees, exact/approximate output, recall behavior, precision,
menu editing, and saving.
The settings file defaults to `calc_term_config.json` beside the script. Choose
another with `python calc_term.py --config my_settings.json`. Validated changes to
options, precision, history recall, syntax colors, custom units, and menus save
immediately. A save error is displayed, preserving the previous file; pending
configuration changes are retried on normal exit. The `:save` command and Save
configuration menu item remain available for a manual retry.

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

Other commands are `:vars`, `:unset NAME`, `:clearvars` (all set variables), `:clear` (history), `:recall result`,
`:recall expression`, `:mode radian`, `:mode degree`, `:format exact`,
`:format approximate`, `:precision DIGITS`, `:help`,
and `:quit`.

For scripting, `--eval` can be repeated; expressions share variables and return a
nonzero exit code on errors:

```powershell
python calc_term.py --eval "3->x" --eval "4*x" --eval "3_in=>_ft"
python -m unittest discover -s tests -v
```
