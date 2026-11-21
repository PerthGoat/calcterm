"""Built-in Math menu entries and their reference metadata."""

# Transcribed from example_files/math_menu.yaml. This module is the runtime
# definition for the Math menu and its Catalog entries.
MATH_MENU = [
    {
        'key': '1',
        'name': 'Number',
        'kind': 'submenu',
        'path': ['1'],
        'description': 'Number mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'exact(',
                'kind': 'function',
                'path': ['1', '1'],
                'arguments': 'expression[, tolerance]',
                'syntax': 'exact(expression[, tolerance])',
                'description': (
                    'Converts approximate numeric values to exact rational or symbolic forms when'
                    ' possible; tolerance controls rational recognition.'
                ),
            },
            {
                'key': '2',
                'function': 'abs(',
                'kind': 'function',
                'path': ['1', '2'],
                'arguments': 'value',
                'syntax': 'abs(value)',
                'description': (
                    'Returns the absolute value of a real number or the modulus of a complex '
                    'number; processes lists and matrices elementwise.'
                ),
            },
            {
                'key': '3',
                'function': 'round(',
                'kind': 'function',
                'path': ['1', '3'],
                'arguments': 'value[, digits]',
                'syntax': 'round(value[, digits])',
                'description': (
                    'Rounds a numeric value to the requested number of decimal places; supports '
                    'lists and matrices.'
                ),
            },
            {
                'key': '4',
                'function': 'iPart(',
                'kind': 'function',
                'path': ['1', '4'],
                'arguments': 'value',
                'syntax': 'iPart(value)',
                'description': 'Returns the integer part of each value by truncation toward zero.',
            },
            {
                'key': '5',
                'function': 'fPart(',
                'kind': 'function',
                'path': ['1', '5'],
                'arguments': 'value',
                'syntax': 'fPart(value)',
                'description': (
                    'Returns the signed fractional part of a value, value minus iPart(value).'
                ),
            },
            {
                'key': '6',
                'function': 'floor(',
                'kind': 'function',
                'path': ['1', '6'],
                'arguments': 'value',
                'syntax': 'floor(value)',
                'description': 'Returns the greatest integer less than or equal to the value.',
            },
            {
                'key': '7',
                'function': 'ceiling(',
                'kind': 'function',
                'path': ['1', '7'],
                'arguments': 'value',
                'syntax': 'ceiling(value)',
                'description': 'Returns the least integer greater than or equal to the value.',
            },
            {
                'key': '8',
                'function': 'sign(',
                'kind': 'function',
                'path': ['1', '8'],
                'arguments': 'value',
                'syntax': 'sign(value)',
                'description': (
                    'Returns the sign of a real number or unit-phase factor of a complex number; '
                    'zero is treated specially.'
                ),
            },
            {
                'key': '9',
                'function': 'mod(',
                'kind': 'function',
                'path': ['1', '9'],
                'arguments': 'dividend, divisor',
                'syntax': 'mod(dividend, divisor)',
                'description': (
                    'Returns a modulo remainder using the modulo, which may differ from remain '
                    'for negative inputs.'
                ),
            },
            {
                'key': 'A',
                'function': 'remain(',
                'kind': 'function',
                'path': ['1', 'A'],
                'arguments': 'dividend, divisor',
                'syntax': 'remain(dividend, divisor)',
                'description': 'Returns the remainder of division using truncated-quotient semantics.',
            },
            {
                'key': 'B',
                'function': 'lcm(',
                'kind': 'function',
                'path': ['1', 'B'],
                'arguments': 'integer1, integer2',
                'syntax': 'lcm(integer1, integer2)',
                'description': (
                    'Returns the least common multiple; also supports corresponding elements of '
                    'lists or matrices.'
                ),
            },
            {
                'key': 'C',
                'function': 'gcd(',
                'kind': 'function',
                'path': ['1', 'C'],
                'arguments': 'integer1, integer2',
                'syntax': 'gcd(integer1, integer2)',
                'description': (
                    'Returns the greatest common divisor; also supports corresponding elements of'
                    ' lists or matrices.'
                ),
            },
            {
                'key': 'D',
                'function': 'root(',
                'kind': 'function',
                'path': ['1', 'D'],
                'arguments': 'radicand, index',
                'syntax': 'root(radicand, index)',
                'description': 'Calculates the specified nth root of an expression.',
                'minimum_os': '3.10',
            },
        ],
    },
    {
        'key': '2',
        'name': 'Angle',
        'kind': 'submenu',
        'path': ['2'],
        'description': 'Angle mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': '°',
                'kind': 'operator',
                'path': ['2', '1'],
                'arguments': 'angle',
                'syntax': 'angle°',
                'description': (
                    'Suffix specifying that the preceding angle is in degrees, overriding the '
                    'current angle mode.'
                ),
            },
            {
                'key': '2',
                'function': 'ʳ',
                'kind': 'operator',
                'path': ['2', '2'],
                'arguments': 'angle',
                'syntax': 'angleʳ',
                'description': (
                    'Superscript-r suffix specifying an angle in radians, irrespective of the '
                    'angle mode.'
                ),
            },
            {
                'key': '3',
                'function': 'P▶Rx(',
                'kind': 'function',
                'path': ['2', '3'],
                'arguments': 'radius, theta',
                'syntax': 'P▶Rx(radius, theta)',
                'description': (
                    'Converts polar coordinates (r, θ) to their rectangular x component, '
                    'r*cos(θ).'
                ),
            },
            {
                'key': '4',
                'function': 'P▶Ry(',
                'kind': 'function',
                'path': ['2', '4'],
                'arguments': 'radius, theta',
                'syntax': 'P▶Ry(radius, theta)',
                'description': (
                    'Converts polar coordinates (r, θ) to their rectangular y component, '
                    'r*sin(θ).'
                ),
            },
            {
                'key': '5',
                'function': 'R▶Pr(',
                'kind': 'function',
                'path': ['2', '5'],
                'arguments': 'x, y',
                'syntax': 'R▶Pr(x, y)',
                'description': 'Converts rectangular coordinates (x,y) to polar radius r.',
            },
            {
                'key': '6',
                'function': 'R▶Pθ(',
                'kind': 'function',
                'path': ['2', '6'],
                'arguments': 'x, y',
                'syntax': 'R▶Pθ(x, y)',
                'description': (
                    'Converts rectangular coordinates (x,y) to polar angle θ using the active '
                    'angle mode.'
                ),
            },
            {
                'key': '7',
                'function': '∠',
                'kind': 'operator',
                'path': ['2', '7'],
                'arguments': 'radius ∠ angle',
                'syntax': 'radius ∠ angle',
                'description': 'Angle separator for entering a complex number in polar form (r∠θ).',
            },
            {
                'key': '8',
                'function': '▶DMS',
                'kind': 'operator',
                'path': ['2', '8'],
                'arguments': 'angle',
                'syntax': 'expression▶DMS',
                'description': (
                    'Displays or converts an angular expression to degrees-minutes-seconds '
                    'notation.'
                ),
            },
            {
                'key': '9',
                'function': '▶DD',
                'kind': 'operator',
                'path': ['2', '9'],
                'arguments': 'angle',
                'syntax': 'expression▶DD',
                'description': 'Converts an angle to decimal-degree representation.',
            },
            {
                'key': 'A',
                'function': '▶Grad',
                'kind': 'operator',
                'path': ['2', 'A'],
                'arguments': 'angle',
                'syntax': 'expression▶Grad',
                'description': 'Converts an angular value to gradians (400 gradians per revolution).',
                'native_path_note': 'MATH > Angle (OS 3.10+)',
                'minimum_os': '3.10',
            },
            {
                'key': 'B',
                'function': '▶Rad',
                'kind': 'operator',
                'path': ['2', 'B'],
                'arguments': 'angle',
                'syntax': 'expression▶Rad',
                'description': 'Converts an angular value to radians.',
                'native_path_note': 'MATH > Angle (OS 3.10+)',
            },
            {
                'key': 'C',
                'function': 'ᵍ',
                'kind': 'operator',
                'path': ['2', 'C'],
                'arguments': 'angle',
                'syntax': 'angleᵍ',
                'description': 'Superscript-g suffix designating an angle in gradians.',
                'native_path_note': 'MATH > Angle',
            },
        ],
    },
    {
        'key': '3',
        'name': 'List',
        'kind': 'submenu',
        'path': ['3'],
        'description': 'List mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'seq(',
                'kind': 'function',
                'path': ['3', '1'],
                'arguments': 'expression, variable, first, last[, step]',
                'syntax': 'seq(expression, variable, first, last[, step])',
                'description': (
                    'Creates a list by evaluating an expression across a sequence of variable '
                    'values.'
                ),
            },
            {
                'key': '2',
                'function': 'min(',
                'kind': 'function',
                'path': ['3', '2'],
                'arguments': 'value1, value2 OR list',
                'syntax': 'min(value1, value2 OR list)',
                'description': (
                    'Finds the smaller of two values or the minimum element of a list; also '
                    'supports elementwise comparisons.'
                ),
            },
            {
                'key': '3',
                'function': 'max(',
                'kind': 'function',
                'path': ['3', '3'],
                'arguments': 'value1, value2 OR list',
                'syntax': 'max(value1, value2 OR list)',
                'description': (
                    'Finds the larger of two values or the maximum element of a list; also '
                    'supports elementwise comparisons.'
                ),
            },
            {
                'key': '4',
                'function': 'SortA',
                'kind': 'command',
                'path': ['3', '4'],
                'arguments': 'listVariable[, companionVariables...]',
                'syntax': 'SortA listVariable[, companionVariables...]',
                'description': (
                    'Sorts an existing list variable in ascending order; optional companion lists'
                    ' receive the same permutation.'
                ),
            },
            {
                'key': '5',
                'function': 'SortD',
                'kind': 'command',
                'path': ['3', '5'],
                'arguments': 'listVariable[, companionVariables...]',
                'syntax': 'SortD listVariable[, companionVariables...]',
                'description': (
                    'Sorts an existing list variable in descending order; optional companion '
                    'lists receive the same permutation.'
                ),
            },
            {
                'key': '6',
                'function': 'sum(',
                'kind': 'function',
                'path': ['3', '6'],
                'arguments': 'list[, start[, end]]',
                'syntax': 'sum(list[, start[, end]])',
                'description': 'Adds the elements of a list, optionally over an index interval.',
            },
            {
                'key': '7',
                'function': 'cumSum(',
                'kind': 'function',
                'path': ['3', '7'],
                'arguments': 'listOrMatrix',
                'syntax': 'cumSum(listOrMatrix)',
                'description': (
                    'Returns cumulative sums, progressively accumulating list entries or matrix '
                    'entries by column.'
                ),
            },
            {
                'key': '8',
                'function': 'product(',
                'kind': 'function',
                'path': ['3', '8'],
                'arguments': 'list[, start[, end]]',
                'syntax': 'product(list[, start[, end]])',
                'description': (
                    'Multiplies elements of a list, optionally using a specified index range.'
                ),
            },
            {
                'key': '9',
                'function': 'left(',
                'kind': 'function',
                'path': ['3', '9'],
                'arguments': 'listOrEquation[, count]',
                'syntax': 'left(listOrEquation[, count])',
                'description': (
                    'Returns leftmost list elements or the left side of an equation or '
                    'inequality.'
                ),
            },
            {
                'key': 'A',
                'function': 'mid(',
                'kind': 'function',
                'path': ['3', 'A'],
                'arguments': 'list, start[, count]',
                'syntax': 'mid(list, start[, count])',
                'description': 'Extracts a portion of a list beginning at a 1-based position.',
            },
            {
                'key': 'B',
                'function': 'right(',
                'kind': 'function',
                'path': ['3', 'B'],
                'arguments': 'listOrEquation[, count]',
                'syntax': 'right(listOrEquation[, count])',
                'description': (
                    'Returns rightmost list elements or the right side of an equation or '
                    'inequality.'
                ),
            },
            {
                'key': 'C',
                'function': 'Δlist(',
                'kind': 'function',
                'path': ['3', 'C'],
                'arguments': 'list',
                'syntax': 'Δlist(list)',
                'description': (
                    'Returns differences between successive list elements; the output has one '
                    'fewer element.'
                ),
            },
            {
                'key': 'D',
                'function': 'polyEval(',
                'kind': 'function',
                'path': ['3', 'D'],
                'arguments': 'coefficients, x',
                'syntax': 'polyEval(coefficients, x)',
                'description': (
                    'Evaluates a polynomial from a list of coefficients in descending-degree '
                    'order at x.'
                ),
            },
            {
                'key': 'E',
                'function': 'list▶mat(',
                'kind': 'function',
                'path': ['3', 'E'],
                'arguments': 'list[, elementsPerRow]',
                'syntax': 'list▶mat(list[, elementsPerRow])',
                'description': (
                    'Converts a list to a matrix, filling rows left-to-right and padding with '
                    'zeros if necessary.'
                ),
            },
            {
                'key': 'F',
                'function': 'mat▶list(',
                'kind': 'function',
                'path': ['3', 'F'],
                'arguments': 'matrix',
                'syntax': 'mat▶list(matrix)',
                'description': 'Flattens a matrix into a list in row-major order.',
            },
        ],
    },
    {
        'key': '4',
        'name': 'Matrix',
        'kind': 'submenu',
        'path': ['4'],
        'description': 'Matrix mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'ᵀ',
                'kind': 'operator',
                'path': ['4', '1'],
                'arguments': 'matrix',
                'syntax': 'matrixᵀ',
                'description': 'Postfix matrix transpose operator; exchanges rows and columns.',
            },
            {
                'key': '2',
                'function': 'det(',
                'kind': 'function',
                'path': ['4', '2'],
                'arguments': 'squareMatrix[, tolerance]',
                'syntax': 'det(squareMatrix[, tolerance])',
                'description': 'Returns the determinant of a square matrix.',
            },
            {
                'key': '3',
                'function': 'ref(',
                'kind': 'function',
                'path': ['4', '3'],
                'arguments': 'matrix[, tolerance]',
                'syntax': 'ref(matrix[, tolerance])',
                'description': 'Returns the row-echelon form of a matrix.',
            },
            {
                'key': '4',
                'function': 'rref(',
                'kind': 'function',
                'path': ['4', '4'],
                'arguments': 'matrix[, tolerance]',
                'syntax': 'rref(matrix[, tolerance])',
                'description': 'Returns the reduced row-echelon form of a matrix.',
            },
            {
                'key': '5',
                'function': 'simult(',
                'kind': 'function',
                'path': ['4', '5'],
                'arguments': 'coefficientMatrix, constants[, tolerance]',
                'syntax': 'simult(coefficientMatrix, constants[, tolerance])',
                'description': (
                    'Solves one or more linear systems A*x=b using the supplied coefficient '
                    'matrix and column vector or matrix.'
                ),
            },
            {
                'key': '6',
                'function': 'identity(',
                'kind': 'function',
                'path': ['4', '6'],
                'arguments': 'size',
                'syntax': 'identity(size)',
                'description': (
                    'Creates a square identity matrix of the given positive integer dimension.'
                ),
            },
            {
                'key': '7',
                'function': 'augment(',
                'kind': 'function',
                'path': ['4', '7'],
                'arguments': 'matrix1, matrix2',
                'syntax': 'augment(matrix1, matrix2)',
                'description': (
                    'Appends columns of the second matrix to the first; may also concatenate '
                    'lists.'
                ),
            },
            {
                'key': '8',
                'function': 'diag(',
                'kind': 'function',
                'path': ['4', '8'],
                'arguments': 'listOrMatrix',
                'syntax': 'diag(listOrMatrix)',
                'description': (
                    "Creates a diagonal matrix from a vector/list, or extracts a square matrix's "
                    'main diagonal.'
                ),
            },
            {
                'key': '9',
                'function': 'eigVl(',
                'kind': 'function',
                'path': ['4', '9'],
                'arguments': 'squareMatrix',
                'syntax': 'eigVl(squareMatrix)',
                'description': 'Returns the eigenvalues of a square real or complex matrix as a list.',
            },
            {
                'key': 'A',
                'function': 'eigVc(',
                'kind': 'function',
                'path': ['4', 'A'],
                'arguments': 'squareMatrix',
                'syntax': 'eigVc(squareMatrix)',
                'description': (
                    'Returns a matrix of eigenvectors for a square matrix, with eigenvectors in '
                    'columns.'
                ),
            },
            {
                'key': 'B',
                'function': 'LU',
                'kind': 'command',
                'path': ['4', 'B'],
                'arguments': 'matrix, lowerVar, upperVar, permutationVar[, tolerance]',
                'syntax': 'LU matrix, lowerVar, upperVar, permutationVar[, tolerance]',
                'description': (
                    'Performs pivoted LU factorization and stores the L, U and permutation '
                    'matrices in named variables.'
                ),
            },
            {
                'key': 'C',
                'function': 'QR',
                'kind': 'command',
                'path': ['4', 'C'],
                'arguments': 'matrix, qVar, rVar[, tolerance]',
                'syntax': 'QR matrix, qVar, rVar[, tolerance]',
                'description': (
                    'Performs QR factorization and stores Q and R in the named matrix variables.'
                ),
            },
            {
                'key': 'D',
                'function': 'Fill',
                'kind': 'command',
                'path': ['4', 'D'],
                'arguments': 'value, existingMatrixOrListVariable',
                'syntax': 'Fill value, existingMatrixOrListVariable',
                'description': (
                    'Replaces every element of an already-existing matrix or list variable with '
                    'one value.'
                ),
            },
            {
                'key': 'E',
                'function': 'randMat(',
                'kind': 'function',
                'path': ['4', 'E'],
                'arguments': 'rows, columns',
                'syntax': 'randMat(rows, columns)',
                'description': (
                    'Creates a rows-by-columns matrix containing random integers from -9 to 9.'
                ),
            },
            {
                'key': 'F',
                'function': 'newMat(',
                'kind': 'function',
                'path': ['4', 'F'],
                'arguments': 'rows, columns',
                'syntax': 'newMat(rows, columns)',
                'description': 'Creates a new zero-filled matrix with the requested dimensions.',
            },
            {
                'key': 'G',
                'function': 'subMat(',
                'kind': 'function',
                'path': ['4', 'G'],
                'arguments': 'matrix, startRow, startColumn[, endRow[, endColumn]]',
                'syntax': 'subMat(matrix, startRow, startColumn[, endRow[, endColumn]])',
                'description': (
                    'Extracts a rectangular submatrix bounded by the supplied row and column '
                    'indices.'
                ),
            },
            {
                'key': 'H',
                'name': 'Norms',
                'kind': 'submenu',
                'path': ['4', 'H'],
                'description': 'Groups the supported matrix-norm operations.',
                'items': [
                    {
                        'key': '1',
                        'function': 'norm(',
                        'kind': 'function',
                        'path': ['4', 'H', '1'],
                        'arguments': 'matrix',
                        'syntax': 'norm(matrix)',
                        'description': (
                            'Returns the Frobenius norm, the square root of the sum of squared '
                            'absolute matrix entries.'
                        ),
                    },
                    {
                        'key': '2',
                        'function': 'rowNorm(',
                        'kind': 'function',
                        'path': ['4', 'H', '2'],
                        'arguments': 'matrix',
                        'syntax': 'rowNorm(matrix)',
                        'description': (
                            'Returns the maximum absolute row sum (infinity norm) of a numeric '
                            'matrix.'
                        ),
                    },
                    {
                        'key': '3',
                        'function': 'colNorm(',
                        'kind': 'function',
                        'path': ['4', 'H', '3'],
                        'arguments': 'matrix',
                        'syntax': 'colNorm(matrix)',
                        'description': (
                            'Returns the maximum absolute column sum (one norm) of a numeric '
                            'matrix.'
                        ),
                    },
                ],
            },
            {
                'key': 'I',
                'name': 'Dimensions',
                'kind': 'submenu',
                'path': ['4', 'I'],
                'description': 'Groups matrix-shape and dimension queries.',
                'items': [
                    {
                        'key': '1',
                        'function': 'dim(',
                        'kind': 'function',
                        'path': ['4', 'I', '1'],
                        'arguments': 'matrixOrList',
                        'syntax': 'dim(matrixOrList)',
                        'description': (
                            'For a matrix, returns a two-element list of row and column counts; '
                            'for a list, returns its length.'
                        ),
                    },
                    {
                        'key': '2',
                        'function': 'rowDim(',
                        'kind': 'function',
                        'path': ['4', 'I', '2'],
                        'arguments': 'matrix',
                        'syntax': 'rowDim(matrix)',
                        'description': 'Returns the number of matrix rows.',
                    },
                    {
                        'key': '3',
                        'function': 'colDim(',
                        'kind': 'function',
                        'path': ['4', 'I', '3'],
                        'arguments': 'matrix',
                        'syntax': 'colDim(matrix)',
                        'description': 'Returns the number of matrix columns.',
                    },
                ],
            },
            {
                'key': 'J',
                'name': 'Row ops',
                'kind': 'submenu',
                'path': ['4', 'J'],
                'description': 'Groups elementary row transformations.',
                'items': [
                    {
                        'key': '1',
                        'function': 'rowSwap(',
                        'kind': 'function',
                        'path': ['4', 'J', '1'],
                        'arguments': 'matrix, row1, row2',
                        'syntax': 'rowSwap(matrix, row1, row2)',
                        'description': 'Returns a matrix with two specified rows interchanged.',
                    },
                    {
                        'key': '2',
                        'function': 'rowAdd(',
                        'kind': 'function',
                        'path': ['4', 'J', '2'],
                        'arguments': 'matrix, sourceRow, targetRow',
                        'syntax': 'rowAdd(matrix, sourceRow, targetRow)',
                        'description': 'Returns a matrix with sourceRow added to targetRow.',
                    },
                    {
                        'key': '3',
                        'function': 'mRow(',
                        'kind': 'function',
                        'path': ['4', 'J', '3'],
                        'arguments': 'multiplier, matrix, row',
                        'syntax': 'mRow(multiplier, matrix, row)',
                        'description': 'Returns a matrix with the given row multiplied by a scalar.',
                    },
                    {
                        'key': '4',
                        'function': 'mRowAdd(',
                        'kind': 'function',
                        'path': ['4', 'J', '4'],
                        'arguments': 'multiplier, matrix, sourceRow, targetRow',
                        'syntax': 'mRowAdd(multiplier, matrix, sourceRow, targetRow)',
                        'description': (
                            'Adds a scalar multiple of sourceRow to targetRow in a new matrix.'
                        ),
                    },
                ],
            },
            {
                'key': 'K',
                'name': 'Element ops',
                'kind': 'submenu',
                'path': ['4', 'K'],
                'description': 'Groups element-by-element matrix arithmetic operators.',
                'items': [
                    {
                        'key': '1',
                        'function': '.+',
                        'kind': 'operator',
                        'path': ['4', 'K', '1'],
                        'arguments': 'left, right',
                        'syntax': 'left .+ right',
                        'description': (
                            'Adds matching matrix elements pairwise or adds a scalar to each '
                            'element.'
                        ),
                    },
                    {
                        'key': '2',
                        'function': '.−',
                        'kind': 'operator',
                        'path': ['4', 'K', '2'],
                        'arguments': 'left, right',
                        'syntax': 'left .− right',
                        'description': (
                            'Subtracts matching matrix elements pairwise or subtracts a scalar '
                            'elementwise.'
                        ),
                    },
                    {
                        'key': '3',
                        'function': '.*',
                        'kind': 'operator',
                        'path': ['4', 'K', '3'],
                        'arguments': 'left, right',
                        'syntax': 'left .* right',
                        'description': (
                            'Multiplies matching matrix elements pairwise (Hadamard product), not'
                            ' matrix multiplication.'
                        ),
                    },
                    {
                        'key': '4',
                        'function': './',
                        'kind': 'operator',
                        'path': ['4', 'K', '4'],
                        'arguments': 'left, right',
                        'syntax': 'left ./ right',
                        'description': (
                            'Divides matching matrix elements pairwise, not matrix inversion.'
                        ),
                    },
                    {
                        'key': '5',
                        'function': '.^',
                        'kind': 'operator',
                        'path': ['4', 'K', '5'],
                        'arguments': 'base, exponent',
                        'syntax': 'base .^ exponent',
                        'description': (
                            'Raises each matrix element to a specified scalar or corresponding '
                            'matrix exponent.'
                        ),
                    },
                ],
            },
            {
                'key': 'L',
                'name': 'Vector ops',
                'kind': 'submenu',
                'path': ['4', 'L'],
                'description': 'Groups vector products, normalization and coordinate conversions.',
                'items': [
                    {
                        'key': '1',
                        'function': 'unitV(',
                        'kind': 'function',
                        'path': ['4', 'L', '1'],
                        'arguments': 'vector',
                        'syntax': 'unitV(vector)',
                        'description': 'Normalizes a row or column vector to unit Euclidean length.',
                    },
                    {
                        'key': '2',
                        'function': 'crossP(',
                        'kind': 'function',
                        'path': ['4', 'L', '2'],
                        'arguments': 'vector1, vector2',
                        'syntax': 'crossP(vector1, vector2)',
                        'description': (
                            'Computes the cross product of two two- or three-component vectors.'
                        ),
                    },
                    {
                        'key': '3',
                        'function': 'dotP(',
                        'kind': 'function',
                        'path': ['4', 'L', '3'],
                        'arguments': 'vector1, vector2',
                        'syntax': 'dotP(vector1, vector2)',
                        'description': 'Returns the dot product of two vectors.',
                    },
                    {
                        'key': '4',
                        'function': '▶Polar',
                        'kind': 'operator',
                        'path': ['4', 'L', '4'],
                        'arguments': 'vectorOrComplexValue',
                        'syntax': 'expression▶Polar',
                        'description': 'Displays a 2D vector or complex value in polar representation.',
                    },
                    {
                        'key': '5',
                        'function': '▶Rect',
                        'kind': 'operator',
                        'path': ['4', 'L', '5'],
                        'arguments': 'vectorOrComplexValue',
                        'syntax': 'expression▶Rect',
                        'description': (
                            'Displays coordinates or a complex value in rectangular '
                            'representation.'
                        ),
                    },
                    {
                        'key': '6',
                        'function': '▶Cylind',
                        'kind': 'operator',
                        'path': ['4', 'L', '6'],
                        'arguments': 'threeComponentVector',
                        'syntax': 'expression▶Cylind',
                        'description': (
                            'Displays a three-dimensional vector in cylindrical coordinates.'
                        ),
                    },
                    {
                        'key': '7',
                        'function': '▶Sphere',
                        'kind': 'operator',
                        'path': ['4', 'L', '7'],
                        'arguments': 'threeComponentVector',
                        'syntax': 'expression▶Sphere',
                        'description': 'Displays a three-dimensional vector in spherical coordinates.',
                    },
                ],
            },
            {
                'key': 'M',
                'function': 'Data▶Mat',
                'kind': 'function',
                'path': ['4', 'M'],
                'arguments': 'dataVariable, matrixVariable[, row1[, col1[, row2[, col2]]]]',
                'syntax': 'Data▶Mat dataVariable, matrixVariable[, row1[, col1[, row2[, col2]]]]',
                'description': (
                    "Creates or updates a matrix variable from a data variable's numeric columns,"
                    ' optionally selecting a rectangular cell range.'
                ),
                'native_path_note': 'MATH > List > data▶mat',
                'outline_correction': (
                    'This is a List conversion command; retained here in Matrix to match the '
                    'requested layout.'
                ),
            },
            {
                'key': 'N',
                'function': 'Mat▶Data',
                'kind': 'function',
                'path': ['4', 'N'],
                'arguments': 'matrix, dataVariable[, row1[, col1[, row2[, col2]]]]',
                'syntax': 'Mat▶Data matrix, dataVariable[, row1[, col1[, row2[, col2]]]]',
                'description': (
                    'Creates a data variable from a numeric matrix, optionally selecting a '
                    'rectangular cell range.'
                ),
                'native_path_note': 'MATH > List > mat▶data',
                'outline_correction': (
                    'This is a List conversion command; retained here in Matrix to match the '
                    'requested layout.'
                ),
            },
        ],
    },
    {
        'key': '5',
        'name': 'Complex',
        'kind': 'submenu',
        'path': ['5'],
        'description': 'Complex mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'conj(',
                'kind': 'function',
                'path': ['5', '1'],
                'arguments': 'complexValue',
                'syntax': 'conj(complexValue)',
                'description': 'Returns the complex conjugate, negating its imaginary component.',
            },
            {
                'key': '2',
                'function': 'real(',
                'kind': 'function',
                'path': ['5', '2'],
                'arguments': 'complexValue',
                'syntax': 'real(complexValue)',
                'description': 'Returns the real component of a complex number.',
            },
            {
                'key': '3',
                'function': 'imag(',
                'kind': 'function',
                'path': ['5', '3'],
                'arguments': 'complexValue',
                'syntax': 'imag(complexValue)',
                'description': 'Returns the imaginary component of a complex number.',
            },
            {
                'key': '4',
                'function': 'angle(',
                'kind': 'function',
                'path': ['5', '4'],
                'arguments': 'complexValue',
                'syntax': 'angle(complexValue)',
                'description': (
                    'Returns the phase or argument of a complex number in the active angle units.'
                ),
            },
            {
                'key': '5',
                'function': 'abs(',
                'kind': 'function',
                'path': ['5', '5'],
                'arguments': 'complexValue',
                'syntax': 'abs(complexValue)',
                'description': 'Returns the magnitude (modulus) of a complex number.',
            },
        ],
    },
    {
        'key': '6',
        'name': 'Statistics',
        'kind': 'submenu',
        'path': ['6'],
        'description': 'Statistics mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'OneVar',
                'kind': 'command',
                'path': ['6', '1'],
                'arguments': 'xList[, frequencyList[, categoryList[, includeCategories]]]',
                'syntax': 'OneVar xList[, frequencyList[, categoryList[, includeCategories]]]',
                'description': (
                    'Computes one-variable summary statistics and stores the results in system '
                    'statistics variables.'
                ),
            },
            {
                'key': '2',
                'function': 'TwoVar',
                'kind': 'command',
                'path': ['6', '2'],
                'arguments': 'xList, yList[, frequencyList[, categoryList[, includeCategories]]]',
                'syntax': 'TwoVar xList, yList[, frequencyList[, categoryList[, includeCategories]]]',
                'description': (
                    'Computes paired two-variable descriptive statistics and stores results in '
                    'system statistics variables.'
                ),
            },
            {
                'key': '3',
                'name': 'Regressions',
                'kind': 'submenu',
                'path': ['6', '3'],
                'description': 'Groups curve-fitting and regression commands operating on paired data.',
                'items': [
                    {
                        'key': '1',
                        'function': 'LinReg',
                        'kind': 'command',
                        'path': ['6', '3', '1'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'LinReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': (
                            'Fits a least-squares linear model y=a*x+b and stores fitted '
                            'coefficients/statistics.'
                        ),
                    },
                    {
                        'key': '2',
                        'function': 'ExpReg',
                        'kind': 'command',
                        'path': ['6', '3', '2'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'ExpReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': (
                            'Fits an exponential model y=a*b^x by transformed least squares.'
                        ),
                    },
                    {
                        'key': '3',
                        'function': 'QuadReg',
                        'kind': 'command',
                        'path': ['6', '3', '3'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'QuadReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': 'Fits the quadratic model y=a*x²+b*x+c.',
                    },
                    {
                        'key': '4',
                        'function': 'PowerReg',
                        'kind': 'command',
                        'path': ['6', '3', '4'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'PowerReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': 'Fits the power model y=a*x^b by logarithmic transformation.',
                    },
                    {
                        'key': '5',
                        'function': 'LnReg',
                        'kind': 'command',
                        'path': ['6', '3', '5'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'LnReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': 'Fits a logarithmic model y=a+b*ln(x).',
                    },
                    {
                        'key': '6',
                        'function': 'MedMed',
                        'kind': 'command',
                        'path': ['6', '3', '6'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'MedMed xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': (
                            'Fits a resistant straight line using median-median summary points.'
                        ),
                    },
                    {
                        'key': '7',
                        'function': 'CubicReg',
                        'kind': 'command',
                        'path': ['6', '3', '7'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'CubicReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': 'Fits a cubic polynomial y=a*x³+b*x²+c*x+d.',
                    },
                    {
                        'key': '8',
                        'function': 'QuartReg',
                        'kind': 'command',
                        'path': ['6', '3', '8'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'QuartReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': 'Fits a quartic polynomial y=a*x⁴+b*x³+c*x²+d*x+e.',
                    },
                    {
                        'key': '9',
                        'function': 'SinReg',
                        'kind': 'command',
                        'path': ['6', '3', '9'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'SinReg xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': (
                            'Fits a sinusoidal model y=a*sin(b*x+c)+d, returning a model in '
                            'radians.'
                        ),
                    },
                    {
                        'key': 'A',
                        'function': 'Logistic',
                        'kind': 'command',
                        'path': ['6', '3', 'A'],
                        'arguments': (
                            'xList, yList[, frequencyList[, categoryList[, includeCategories]]]'
                        ),
                        'syntax': (
                            'Logistic xList, yList[, frequencyList[, categoryList[, '
                            'includeCategories]]]'
                        ),
                        'description': 'Fits a logistic S-shaped curve to paired observations.',
                    },
                ],
            },
            {
                'key': '4',
                'function': 'mean(',
                'kind': 'function',
                'path': ['6', '4'],
                'arguments': 'list[, frequencies]',
                'syntax': 'mean(list[, frequencies])',
                'description': 'Returns the arithmetic mean (or weighted arithmetic mean) of the data.',
            },
            {
                'key': '5',
                'function': 'variance(',
                'kind': 'function',
                'path': ['6', '5'],
                'arguments': 'list[, frequencies]',
                'syntax': 'variance(list[, frequencies])',
                'description': 'Returns the sample variance of the data.',
            },
            {
                'key': '6',
                'function': 'stdDev(',
                'kind': 'function',
                'path': ['6', '6'],
                'arguments': 'list[, frequencies]',
                'syntax': 'stdDev(list[, frequencies])',
                'description': 'Returns the sample standard deviation of the data.',
            },
            {
                'key': '7',
                'function': 'stDevPop(',
                'kind': 'function',
                'path': ['6', '7'],
                'arguments': 'list[, frequencies]',
                'syntax': 'stDevPop(list[, frequencies])',
                'description': 'Returns the population standard deviation of the data.',
                'minimum_os': '3.10',
            },
            {
                'key': '8',
                'function': 'median(',
                'kind': 'function',
                'path': ['6', '8'],
                'arguments': 'list[, frequencies]',
                'syntax': 'median(list[, frequencies])',
                'description': 'Returns the median of the ordered data.',
            },
            {
                'key': '9',
                'function': 'ShowStat',
                'kind': 'command',
                'path': ['6', '9'],
                'arguments': None,
                'syntax': 'ShowStat',
                'description': (
                    'Opens the statistics results screen for the most recent OneVar, TwoVar or '
                    'regression operation.'
                ),
            },
        ],
    },
    {
        'key': '7',
        'name': 'Probability',
        'kind': 'submenu',
        'path': ['7'],
        'description': 'Probability mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': '!',
                'kind': 'operator',
                'path': ['7', '1'],
                'arguments': 'nonnegativeInteger',
                'syntax': 'n!',
                'description': (
                    'Postfix factorial operator; multiplies all positive integers up to n, with '
                    '0! = 1.'
                ),
            },
            {
                'key': '2',
                'function': 'nPr(',
                'kind': 'function',
                'path': ['7', '2'],
                'arguments': 'n, r',
                'syntax': 'nPr(n, r)',
                'description': (
                    'Returns the number of permutations of r objects selected from n: n!/(n-r)!.'
                ),
            },
            {
                'key': '3',
                'function': 'nCr(',
                'kind': 'function',
                'path': ['7', '3'],
                'arguments': 'n, r',
                'syntax': 'nCr(n, r)',
                'description': (
                    'Returns the number of combinations of r objects selected from n: '
                    'n!/(r!*(n-r)!).'
                ),
            },
            {
                'key': '4',
                'function': 'rand(',
                'kind': 'function',
                'path': ['7', '4'],
                'arguments': '[integerBound]',
                'syntax': 'rand([integerBound])',
                'description': (
                    'With no argument returns a pseudorandom real in [0,1); with integer n '
                    'returns a pseudorandom integer in a signed range determined by n.'
                ),
            },
            {
                'key': '5',
                'function': 'randNorm(',
                'kind': 'function',
                'path': ['7', '5'],
                'arguments': 'mean, standardDeviation',
                'syntax': 'randNorm(mean, standardDeviation)',
                'description': (
                    'Returns a pseudorandom sample from a normal distribution with the specified '
                    'mean and standard deviation.'
                ),
            },
            {
                'key': '6',
                'function': 'RandSeed',
                'kind': 'command',
                'path': ['7', '6'],
                'arguments': 'seed',
                'syntax': 'RandSeed seed',
                'description': (
                    'Sets the pseudorandom-number generator seed; a seed of zero restores the '
                    'default seeds.'
                ),
            },
            {
                'key': '7',
                'function': 'randMat(',
                'kind': 'function',
                'path': ['7', '7'],
                'arguments': 'rows, columns',
                'syntax': 'randMat(rows, columns)',
                'description': (
                    'Returns a matrix of uniformly generated random integers between -9 and 9.'
                ),
            },
            {
                'key': '8',
                'function': 'randPoly(',
                'kind': 'function',
                'path': ['7', '8'],
                'arguments': 'variable, order',
                'syntax': 'randPoly(variable, order)',
                'description': (
                    'Creates a polynomial of the specified degree with random integer '
                    'coefficients between -9 and 9.'
                ),
            },
        ],
    },
    {
        'key': '8',
        'name': 'Test',
        'kind': 'submenu',
        'path': ['8'],
        'description': 'Test mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': '>',
                'kind': 'operator',
                'path': ['8', '1'],
                'arguments': 'left, right',
                'syntax': 'left > right',
                'description': 'True if the left operand is greater than the right operand.',
            },
            {
                'key': '2',
                'function': '<',
                'kind': 'operator',
                'path': ['8', '2'],
                'arguments': 'left, right',
                'syntax': 'left < right',
                'description': 'True if the left operand is less than the right operand.',
            },
            {
                'key': '3',
                'function': '≥',
                'kind': 'operator',
                'path': ['8', '3'],
                'arguments': 'left, right',
                'syntax': 'left ≥ right',
                'description': (
                    'True if the left operand is greater than or equal to the right operand.'
                ),
            },
            {
                'key': '4',
                'function': '≤',
                'kind': 'operator',
                'path': ['8', '4'],
                'arguments': 'left, right',
                'syntax': 'left ≤ right',
                'description': 'True if the left operand is less than or equal to the right operand.',
            },
            {
                'key': '5',
                'function': '=',
                'kind': 'operator',
                'path': ['8', '5'],
                'arguments': 'left, right',
                'syntax': 'left = right',
                'description': 'True if two values or expressions are equal.',
            },
            {
                'key': '6',
                'function': '≠',
                'kind': 'operator',
                'path': ['8', '6'],
                'arguments': 'left, right',
                'syntax': 'left ≠ right',
                'description': 'True if two values or expressions are not equal.',
            },
            {
                'key': '7',
                'function': 'not',
                'kind': 'operator',
                'path': ['8', '7'],
                'arguments': 'booleanOrInteger',
                'syntax': 'not booleanOrInteger',
                'description': (
                    'Negates a Boolean proposition; for an integer, computes bitwise '
                    'ones-complement.'
                ),
            },
            {
                'key': '8',
                'function': 'and',
                'kind': 'operator',
                'path': ['8', '8'],
                'arguments': 'left, right',
                'syntax': 'left and right',
                'description': (
                    'Logical conjunction for Boolean conditions or bitwise AND of integer '
                    'operands.'
                ),
            },
            {
                'key': '9',
                'function': 'or',
                'kind': 'operator',
                'path': ['8', '9'],
                'arguments': 'left, right',
                'syntax': 'left or right',
                'description': (
                    'Logical disjunction for Boolean conditions or bitwise OR of integer '
                    'operands.'
                ),
            },
            {
                'key': 'A',
                'function': 'xor',
                'kind': 'operator',
                'path': ['8', 'A'],
                'arguments': 'left, right',
                'syntax': 'left xor right',
                'description': (
                    'Exclusive OR of Boolean conditions or bitwise XOR for integer operands.'
                ),
            },
            {
                'key': 'B',
                'function': 'isPrime(',
                'kind': 'function',
                'path': ['8', 'B'],
                'arguments': 'integer',
                'syntax': 'isPrime(integer)',
                'description': 'Tests whether an integer is prime, returning true or false.',
            },
        ],
    },
    {
        'key': '9',
        'name': 'Algebra',
        'kind': 'submenu',
        'path': ['9'],
        'description': 'Algebra mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'solve(',
                'kind': 'function',
                'path': ['9', '1'],
                'arguments': 'equationOrInequality, variable',
                'syntax': 'solve(equationOrInequality, variable)',
                'description': (
                    'Symbolically finds real solutions of an equation, inequality or system for '
                    'specified variable(s).'
                ),
            },
            {
                'key': '2',
                'function': 'factor(',
                'kind': 'function',
                'path': ['9', '2'],
                'arguments': 'expression[, variable]',
                'syntax': 'factor(expression[, variable])',
                'description': (
                    'Factors an integer, polynomial or rational expression in exact arithmetic.'
                ),
            },
            {
                'key': '3',
                'function': 'expand(',
                'kind': 'function',
                'path': ['9', '3'],
                'arguments': 'expression[, variable]',
                'syntax': 'expand(expression[, variable])',
                'description': (
                    'Distributes products and powers to obtain an expanded symbolic expression.'
                ),
            },
            {
                'key': '4',
                'function': 'zeros(',
                'kind': 'function',
                'path': ['9', '4'],
                'arguments': 'expression, variable',
                'syntax': 'zeros(expression, variable)',
                'description': (
                    'Returns a list of real zeros of an expression with respect to a variable.'
                ),
            },
            {
                'key': '5',
                'function': 'approx(',
                'kind': 'function',
                'path': ['9', '5'],
                'arguments': 'expression',
                'syntax': 'approx(expression)',
                'description': 'Forces a numerical or approximate evaluation of an expression.',
            },
            {
                'key': '6',
                'function': 'comDenom(',
                'kind': 'function',
                'path': ['9', '6'],
                'arguments': 'rationalExpression[, variable]',
                'syntax': 'comDenom(rationalExpression[, variable])',
                'description': (
                    'Combines terms over a common denominator, optionally collecting powers of a '
                    'specified variable.'
                ),
            },
            {
                'key': '7',
                'function': 'propFrac(',
                'kind': 'function',
                'path': ['9', '7'],
                'arguments': 'rationalExpression[, variable]',
                'syntax': 'propFrac(rationalExpression[, variable])',
                'description': (
                    'Rewrites an improper rational expression as a polynomial or integer part '
                    'plus a proper fractional part.'
                ),
            },
            {
                'key': '8',
                'function': 'nSolve(',
                'kind': 'function',
                'path': ['9', '8'],
                'arguments': 'equation, variableOrGuess',
                'syntax': 'nSolve(equation, variableOrGuess)',
                'description': (
                    'Numerically finds a real solution of an equation, optionally using a '
                    'variable assignment as an initial guess.'
                ),
            },
            {
                'key': '9',
                'name': 'Trig',
                'kind': 'submenu',
                'path': ['9', '9'],
                'description': (
                    'Native Algebra submenu for symbolic trigonometric expansion and collection; '
                    'distinct from the top-level Trig menu.'
                ),
                'items': [
                    {
                        'key': '1',
                        'function': 'tExpand(',
                        'kind': 'function',
                        'path': ['9', '9', '1'],
                        'arguments': 'expression',
                        'syntax': 'tExpand(expression)',
                        'description': 'Expands trigonometric multiple-angle and sum/difference forms.',
                    },
                    {
                        'key': '2',
                        'function': 'tCollect(',
                        'kind': 'function',
                        'path': ['9', '9', '2'],
                        'arguments': 'expression',
                        'syntax': 'tCollect(expression)',
                        'description': (
                            'Collects products and powers of trigonometric terms into '
                            'multiple-angle/sum forms.'
                        ),
                    },
                ],
            },
            {
                'key': 'A',
                'name': 'Complex',
                'kind': 'submenu',
                'path': ['9', 'A'],
                'description': 'Groups symbolic solving and factorization over complex numbers.',
                'items': [
                    {
                        'key': '1',
                        'function': 'cSolve(',
                        'kind': 'function',
                        'path': ['9', 'A', '1'],
                        'arguments': 'equation, variable',
                        'syntax': 'cSolve(equation, variable)',
                        'description': 'Symbolically finds real and complex solutions of an equation.',
                    },
                    {
                        'key': '2',
                        'function': 'cFactor(',
                        'kind': 'function',
                        'path': ['9', 'A', '2'],
                        'arguments': 'expression[, variable]',
                        'syntax': 'cFactor(expression[, variable])',
                        'description': 'Factors expressions over the complex numbers when possible.',
                        'outline_correction': 'Added/normalized from the TI manual for completeness.',
                    },
                    {
                        'key': '3',
                        'function': 'cZeros(',
                        'kind': 'function',
                        'path': ['9', 'A', '3'],
                        'arguments': 'expression, variable',
                        'syntax': 'cZeros(expression, variable)',
                        'description': 'Returns candidate complex zeros of an expression.',
                    },
                ],
            },
            {
                'key': 'B',
                'name': 'Extract',
                'kind': 'submenu',
                'path': ['9', 'B'],
                'description': 'Groups numerator, denominator and equation-side extraction.',
                'items': [
                    {
                        'key': '1',
                        'function': 'getNum(',
                        'kind': 'function',
                        'path': ['9', 'B', '1'],
                        'arguments': 'expression',
                        'syntax': 'getNum(expression)',
                        'description': (
                            'Returns the numerator of a rational expression after appropriate '
                            'normalization.'
                        ),
                    },
                    {
                        'key': '2',
                        'function': 'getDenom(',
                        'kind': 'function',
                        'path': ['9', 'B', '2'],
                        'arguments': 'expression',
                        'syntax': 'getDenom(expression)',
                        'description': (
                            'Returns the denominator of a rational expression after appropriate '
                            'normalization.'
                        ),
                    },
                    {
                        'key': '3',
                        'function': 'left(',
                        'kind': 'function',
                        'path': ['9', 'B', '3'],
                        'arguments': 'equationOrInequality',
                        'syntax': 'left(equationOrInequality)',
                        'description': 'Extracts the left side of an equation or inequality.',
                    },
                    {
                        'key': '4',
                        'function': 'right(',
                        'kind': 'function',
                        'path': ['9', 'B', '4'],
                        'arguments': 'equationOrInequality',
                        'syntax': 'right(equationOrInequality)',
                        'description': 'Extracts the right side of an equation or inequality.',
                    },
                ],
            },
        ],
    },
    {
        'key': 'A',
        'name': 'Trig',
        'kind': 'submenu',
        'path': ['A'],
        'description': (
            'Native top-level MATH Trig menu for trigonometric and inverse trigonometric '
            'functions.'
        ),
        'items': [
            {
                'key': '1',
                'function': 'sin(',
                'kind': 'function',
                'path': ['A', '1'],
                'arguments': 'angle',
                'syntax': 'sin(angle)',
                'description': 'Returns the sine of an angle.',
            },
            {
                'key': '2',
                'function': 'cos(',
                'kind': 'function',
                'path': ['A', '2'],
                'arguments': 'angle',
                'syntax': 'cos(angle)',
                'description': 'Returns the cosine of an angle.',
            },
            {
                'key': '3',
                'function': 'tan(',
                'kind': 'function',
                'path': ['A', '3'],
                'arguments': 'angle',
                'syntax': 'tan(angle)',
                'description': 'Returns the tangent of an angle.',
            },
            {
                'key': '4',
                'function': 'csc(',
                'kind': 'function',
                'path': ['A', '4'],
                'arguments': 'angle',
                'syntax': 'csc(angle)',
                'description': 'Returns the cosecant, 1/sin(angle).',
            },
            {
                'key': '5',
                'function': 'sec(',
                'kind': 'function',
                'path': ['A', '5'],
                'arguments': 'angle',
                'syntax': 'sec(angle)',
                'description': 'Returns the secant, 1/cos(angle).',
            },
            {
                'key': '6',
                'function': 'cot(',
                'kind': 'function',
                'path': ['A', '6'],
                'arguments': 'angle',
                'syntax': 'cot(angle)',
                'description': 'Returns the cotangent, 1/tan(angle).',
            },
            {
                'key': '7',
                'function': 'sin⁻¹(',
                'kind': 'function',
                'path': ['A', '7'],
                'arguments': 'value',
                'syntax': 'sin⁻¹(value)',
                'description': 'Returns the inverse sine (principal arcsine), not reciprocal sine.',
            },
            {
                'key': '8',
                'function': 'cos⁻¹(',
                'kind': 'function',
                'path': ['A', '8'],
                'arguments': 'value',
                'syntax': 'cos⁻¹(value)',
                'description': (
                    'Returns the inverse cosine (principal arccosine), not reciprocal cosine.'
                ),
            },
            {
                'key': '9',
                'function': 'tan⁻¹(',
                'kind': 'function',
                'path': ['A', '9'],
                'arguments': 'value',
                'syntax': 'tan⁻¹(value)',
                'description': (
                    'Returns the inverse tangent (principal arctangent), not reciprocal tangent.'
                ),
            },
            {
                'key': 'A',
                'function': 'csc⁻¹(',
                'kind': 'function',
                'path': ['A', 'A'],
                'arguments': 'value',
                'syntax': 'csc⁻¹(value)',
                'description': 'Returns the inverse cosecant (principal arccosecant).',
            },
            {
                'key': 'B',
                'function': 'sec⁻¹(',
                'kind': 'function',
                'path': ['A', 'B'],
                'arguments': 'value',
                'syntax': 'sec⁻¹(value)',
                'description': 'Returns the inverse secant (principal arcsecant).',
            },
            {
                'key': 'C',
                'function': 'cot⁻¹(',
                'kind': 'function',
                'path': ['A', 'C'],
                'arguments': 'value',
                'syntax': 'cot⁻¹(value)',
                'description': 'Returns the inverse cotangent (principal arccotangent).',
            },
        ],
    },
    {
        'key': 'B',
        'name': 'Calculus',
        'kind': 'submenu',
        'path': ['B'],
        'description': 'Calculus mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'd(',
                'kind': 'function',
                'path': ['B', '1'],
                'arguments': 'expression, variable[, order]',
                'syntax': 'd(expression, variable[, order])',
                'description': (
                    'Performs symbolic differentiation with respect to a variable; optional order'
                    ' selects derivative order.'
                ),
            },
            {
                'key': '2',
                'function': '∫(',
                'kind': 'function',
                'path': ['B', '2'],
                'arguments': 'expression, variable[, lowerBound, upperBound]',
                'syntax': '∫(expression, variable[, lowerBound, upperBound])',
                'description': (
                    'Computes an indefinite symbolic integral or a definite integral between '
                    'bounds.'
                ),
            },
            {
                'key': '3',
                'function': 'limit(',
                'kind': 'function',
                'path': ['B', '3'],
                'arguments': 'expression, variable, point[, direction]',
                'syntax': 'limit(expression, variable, point[, direction])',
                'description': (
                    'Evaluates a limit as a variable approaches a point; direction optionally '
                    'selects left or right limit.'
                ),
            },
            {
                'key': '4',
                'function': 'Σ(',
                'kind': 'function',
                'path': ['B', '4'],
                'arguments': 'expression, indexVariable, lower, upper',
                'syntax': 'Σ(expression, indexVariable, lower, upper)',
                'description': (
                    'Computes a symbolic or numeric finite/infinite summation over an index.'
                ),
            },
            {
                'key': '5',
                'function': 'Π(',
                'kind': 'function',
                'path': ['B', '5'],
                'arguments': 'expression, indexVariable, lower, upper',
                'syntax': 'Π(expression, indexVariable, lower, upper)',
                'description': 'Computes a product of terms over a range of index values.',
            },
            {
                'key': '6',
                'function': 'fMin(',
                'kind': 'function',
                'path': ['B', '6'],
                'arguments': 'expression, variable',
                'syntax': 'fMin(expression, variable)',
                'description': (
                    'Finds candidate locations of a minimum or greatest lower bound; output can '
                    'be a symbolic condition.'
                ),
            },
            {
                'key': '7',
                'function': 'fMax(',
                'kind': 'function',
                'path': ['B', '7'],
                'arguments': 'expression, variable',
                'syntax': 'fMax(expression, variable)',
                'description': (
                    'Finds candidate locations of a maximum or least upper bound; output can be a'
                    ' symbolic condition.'
                ),
            },
            {
                'key': '8',
                'function': 'arcLen(',
                'kind': 'function',
                'path': ['B', '8'],
                'arguments': 'expression, variable, lower, upper',
                'syntax': 'arcLen(expression, variable, lower, upper)',
                'description': 'Computes arc length of the graph of an expression over an interval.',
            },
            {
                'key': '9',
                'function': 'taylor(',
                'kind': 'function',
                'path': ['B', '9'],
                'arguments': 'expression, variable, order[, center]',
                'syntax': 'taylor(expression, variable, order[, center])',
                'description': (
                    'Computes a Taylor polynomial of specified order around a center (default '
                    'zero).'
                ),
            },
            {
                'key': 'A',
                'function': 'nDeriv(',
                'kind': 'function',
                'path': ['B', 'A'],
                'arguments': 'expression, variable[, h]',
                'syntax': 'nDeriv(expression, variable[, h])',
                'description': (
                    'Estimates the derivative expression using a central finite-difference '
                    'quotient with optional step size h (default 0.001); evaluate the result at a'
                    ' point by assigning a value to the variable.'
                ),
            },
            {
                'key': 'B',
                'function': 'nInt(',
                'kind': 'function',
                'path': ['B', 'B'],
                'arguments': 'expression, variable, lower, upper',
                'syntax': 'nInt(expression, variable, lower, upper)',
                'description': 'Approximates a definite integral numerically by adaptive quadrature.',
            },
            {
                'key': 'C',
                'function': 'deSolve(',
                'kind': 'function',
                'path': ['B', 'C'],
                'arguments': 'differentialEquation, independentVariable, dependentVariable',
                'syntax': 'deSolve(differentialEquation, independentVariable, dependentVariable)',
                'description': (
                    'Symbolically solves a first- or second-order ordinary differential equation,'
                    ' optionally with conditions.'
                ),
            },
            {
                'key': 'D',
                'function': 'impDif(',
                'kind': 'function',
                'path': ['B', 'D'],
                'arguments': 'equation, independentVariable, dependentVariable',
                'syntax': 'impDif(equation, independentVariable, dependentVariable)',
                'description': (
                    'Finds the implicit derivative of the dependent variable defined by an '
                    'equation.'
                ),
                'minimum_os': '3.10',
            },
        ],
    },
    {
        'key': 'C',
        'name': 'Hyperbolic',
        'kind': 'submenu',
        'path': ['C'],
        'description': 'Hyperbolic mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'sinh(',
                'kind': 'function',
                'path': ['C', '1'],
                'arguments': 'value',
                'syntax': 'sinh(value)',
                'description': 'Returns the hyperbolic sine.',
            },
            {
                'key': '2',
                'function': 'cosh(',
                'kind': 'function',
                'path': ['C', '2'],
                'arguments': 'value',
                'syntax': 'cosh(value)',
                'description': 'Returns the hyperbolic cosine.',
            },
            {
                'key': '3',
                'function': 'tanh(',
                'kind': 'function',
                'path': ['C', '3'],
                'arguments': 'value',
                'syntax': 'tanh(value)',
                'description': 'Returns the hyperbolic tangent.',
            },
            {
                'key': '4',
                'function': 'csch(',
                'kind': 'function',
                'path': ['C', '4'],
                'arguments': 'value',
                'syntax': 'csch(value)',
                'description': 'Returns the hyperbolic cosecant, 1/sinh(value).',
            },
            {
                'key': '5',
                'function': 'sech(',
                'kind': 'function',
                'path': ['C', '5'],
                'arguments': 'value',
                'syntax': 'sech(value)',
                'description': 'Returns the hyperbolic secant, 1/cosh(value).',
            },
            {
                'key': '6',
                'function': 'coth(',
                'kind': 'function',
                'path': ['C', '6'],
                'arguments': 'value',
                'syntax': 'coth(value)',
                'description': 'Returns the hyperbolic cotangent, 1/tanh(value).',
            },
            {
                'key': '7',
                'function': 'sinh⁻¹(',
                'kind': 'function',
                'path': ['C', '7'],
                'arguments': 'value',
                'syntax': 'sinh⁻¹(value)',
                'description': 'Returns the inverse hyperbolic sine (asinh).',
            },
            {
                'key': '8',
                'function': 'cosh⁻¹(',
                'kind': 'function',
                'path': ['C', '8'],
                'arguments': 'value',
                'syntax': 'cosh⁻¹(value)',
                'description': 'Returns the inverse hyperbolic cosine (acosh).',
            },
            {
                'key': '9',
                'function': 'tanh⁻¹(',
                'kind': 'function',
                'path': ['C', '9'],
                'arguments': 'value',
                'syntax': 'tanh⁻¹(value)',
                'description': 'Returns the inverse hyperbolic tangent (atanh).',
            },
            {
                'key': 'A',
                'function': 'csch⁻¹(',
                'kind': 'function',
                'path': ['C', 'A'],
                'arguments': 'value',
                'syntax': 'csch⁻¹(value)',
                'description': 'Returns the inverse hyperbolic cosecant.',
            },
            {
                'key': 'B',
                'function': 'sech⁻¹(',
                'kind': 'function',
                'path': ['C', 'B'],
                'arguments': 'value',
                'syntax': 'sech⁻¹(value)',
                'description': 'Returns the inverse hyperbolic secant.',
            },
            {
                'key': 'C',
                'function': 'coth⁻¹(',
                'kind': 'function',
                'path': ['C', 'C'],
                'arguments': 'value',
                'syntax': 'coth⁻¹(value)',
                'description': 'Returns the inverse hyperbolic cotangent.',
            },
        ],
    },
    {
        'key': 'D',
        'name': 'String',
        'kind': 'submenu',
        'path': ['D'],
        'description': 'String mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': 'string(',
                'kind': 'function',
                'path': ['D', '1'],
                'arguments': 'expression',
                'syntax': 'string(expression)',
                'description': 'Converts the simplified value of an expression into text.',
            },
            {
                'key': '2',
                'function': 'expr(',
                'kind': 'function',
                'path': ['D', '2'],
                'arguments': 'text',
                'syntax': 'expr(text)',
                'description': 'Parses a string containing a valid expression and evaluates it.',
            },
            {
                'key': '3',
                'function': 'dim(',
                'kind': 'function',
                'path': ['D', '3'],
                'arguments': 'text',
                'syntax': 'dim(text)',
                'description': (
                    'Returns the length of a character string; also applies to lists or matrices.'
                ),
            },
            {
                'key': '4',
                'function': '&',
                'kind': 'operator',
                'path': ['D', '4'],
                'arguments': 'leftText, rightText',
                'syntax': 'leftText & rightText',
                'description': 'Infix string concatenation operator joining two text values.',
            },
            {
                'key': '5',
                'function': 'mid(',
                'kind': 'function',
                'path': ['D', '5'],
                'arguments': 'text, start[, count]',
                'syntax': 'mid(text, start[, count])',
                'description': (
                    'Extracts a substring beginning at a 1-based position, optionally limiting '
                    'its length.'
                ),
            },
            {
                'key': '6',
                'function': 'inString(',
                'kind': 'function',
                'path': ['D', '6'],
                'arguments': 'sourceText, targetText[, start]',
                'syntax': 'inString(sourceText, targetText[, start])',
                'description': 'Finds the 1-based location of a substring; returns zero if not found.',
            },
            {
                'key': '7',
                'function': 'left(',
                'kind': 'function',
                'path': ['D', '7'],
                'arguments': 'text[, count]',
                'syntax': 'left(text[, count])',
                'description': 'Returns the first count characters of a string.',
            },
            {
                'key': '8',
                'function': 'right(',
                'kind': 'function',
                'path': ['D', '8'],
                'arguments': 'text[, count]',
                'syntax': 'right(text[, count])',
                'description': 'Returns the last count characters of a string.',
            },
            {
                'key': '9',
                'function': 'format(',
                'kind': 'function',
                'path': ['D', '9'],
                'arguments': 'value[, formatString]',
                'syntax': 'format(value[, formatString])',
                'description': (
                    'Formats a numeric expression into a string, including precision, radix, '
                    'grouping and notation choices.'
                ),
            },
            {
                'key': 'A',
                'function': 'char(',
                'kind': 'function',
                'path': ['D', 'A'],
                'arguments': 'characterCode',
                'syntax': 'char(characterCode)',
                'description': (
                    'Returns the character for a calculator character-set code from 0 through '
                    '255.'
                ),
            },
            {
                'key': 'B',
                'function': 'ord(',
                'kind': 'function',
                'path': ['D', 'B'],
                'arguments': 'text',
                'syntax': 'ord(text)',
                'description': 'Returns the character-set code of the first character of a string.',
            },
        ],
    },
    {
        'key': 'E',
        'name': 'Base',
        'kind': 'submenu',
        'path': ['E'],
        'description': 'Base mathematical functions, commands and operators.',
        'items': [
            {
                'key': '1',
                'function': '▶ln',
                'kind': 'operator',
                'path': ['E', '1'],
                'arguments': 'expression',
                'syntax': 'expression▶ln',
                'description': 'Rewrites logarithmic terms of an expression in natural-logarithm form.',
                'native_path_note': 'MATH > Base (OS 3.10+)',
                'minimum_os': '3.10',
            },
            {
                'key': '2',
                'function': '▶logbase(',
                'kind': 'operator',
                'path': ['E', '2'],
                'arguments': 'base (postfix operand: expression to the left)',
                'syntax': 'expression▶logbase(base)',
                'description': (
                    'Rewrites logarithmic terms in the expression to the left using logarithms in'
                    ' the specified base; it does not directly compute a logarithm.'
                ),
                'native_path_note': 'MATH > Base (OS 3.10+)',
                'minimum_os': '3.10',
            },
            {
                'key': '3',
                'function': '▶Hex',
                'kind': 'operator',
                'path': ['E', '3'],
                'arguments': 'integer',
                'syntax': 'expression▶Hex',
                'description': 'Displays or converts an integer in base 16 using the 0h prefix.',
            },
            {
                'key': '4',
                'function': '▶Bin',
                'kind': 'operator',
                'path': ['E', '4'],
                'arguments': 'integer',
                'syntax': 'expression▶Bin',
                'description': 'Displays or converts an integer in base 2 using the 0b prefix.',
            },
            {
                'key': '5',
                'function': '▶Dec',
                'kind': 'operator',
                'path': ['E', '5'],
                'arguments': 'integer',
                'syntax': 'expression▶Dec',
                'description': 'Displays or converts an integer in base 10.',
            },
            {
                'key': '6',
                'function': 'and',
                'kind': 'operator',
                'path': ['E', '6'],
                'arguments': 'integer1, integer2',
                'syntax': 'integer1 and integer2',
                'description': 'Performs bitwise AND on signed 32-bit integer operands.',
            },
            {
                'key': '7',
                'function': 'or',
                'kind': 'operator',
                'path': ['E', '7'],
                'arguments': 'integer1, integer2',
                'syntax': 'integer1 or integer2',
                'description': 'Performs bitwise OR on signed 32-bit integer operands.',
            },
            {
                'key': '8',
                'function': 'xor',
                'kind': 'operator',
                'path': ['E', '8'],
                'arguments': 'integer1, integer2',
                'syntax': 'integer1 xor integer2',
                'description': 'Performs bitwise exclusive OR on signed 32-bit integer operands.',
            },
            {
                'key': '9',
                'function': 'not',
                'kind': 'operator',
                'path': ['E', '9'],
                'arguments': 'integer',
                'syntax': 'not integer',
                'description': 'Computes the bitwise ones-complement of a signed 32-bit integer.',
            },
            {
                'key': 'A',
                'function': '−',
                'kind': 'operator',
                'path': ['E', 'A'],
                'arguments': 'integer',
                'syntax': '−integer',
                'description': (
                    'Unary negation of a signed integer; corresponds to twos-complement negation '
                    'when represented in binary.'
                ),
            },
            {
                'key': 'B',
                'function': 'shift(',
                'kind': 'function',
                'path': ['E', 'B'],
                'arguments': 'integer[, bitCount]',
                'syntax': 'shift(integer[, bitCount])',
                'description': (
                    "Shifts a signed 32-bit integer's bits; a negative count shifts right, while "
                    'a positive count shifts left.'
                ),
            },
            {
                'key': 'C',
                'function': 'rotate(',
                'kind': 'function',
                'path': ['E', 'C'],
                'arguments': 'integer[, bitCount]',
                'syntax': 'rotate(integer[, bitCount])',
                'description': (
                    'Rotates bits within a 32-bit integer by a specified number of positions.'
                ),
            },
        ],
    },
]
