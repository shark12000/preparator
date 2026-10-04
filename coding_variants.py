from collections import Counter, deque
from math import factorial


VARIATIONS_PER_ARCHETYPE = 13


def _count_vowels(text):
    return sum(character.casefold() in "aeiou" for character in text)


def _is_palindrome(text):
    normalized = "".join(character.casefold() for character in text if character.isalnum())
    return normalized == normalized[::-1]


def _first_unique(text):
    counts = Counter(text)
    return next((character for character in text if counts[character] == 1), None)


def _balanced_brackets(text):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for character in text:
        if character in "([{":
            stack.append(character)
        elif character in pairs and (not stack or stack.pop() != pairs[character]):
            return False
    return not stack


def _missing_number(values):
    upper = len(values) + 1
    return upper * (upper + 1) // 2 - sum(values)


def _most_frequent(values):
    counts = Counter(values)
    return max(counts, key=counts.get) if counts else None


def _rotate_right(values, amount):
    if not values:
        return []
    amount %= len(values)
    return values[-amount:] + values[:-amount] if amount else values[:]


def _two_sum(values, target):
    seen = {}
    for index, value in enumerate(values):
        complement = target - value
        if complement in seen:
            return [seen[complement], index]
        seen[value] = index
    return None


def _max_profit(prices):
    lowest = float("inf")
    best = 0
    for price in prices:
        best = max(best, price - lowest)
        lowest = min(lowest, price)
    return best


def _count_change(coins, amount):
    ways = [0] * (amount + 1)
    ways[0] = 1
    for coin in coins:
        for subtotal in range(coin, amount + 1):
            ways[subtotal] += ways[subtotal - coin]
    return ways[amount]


def _can_segment(text, words):
    reachable = [False] * (len(text) + 1)
    reachable[0] = True
    for end in range(1, len(text) + 1):
        reachable[end] = any(
            reachable[start] and text[start:end] in words for start in range(end)
        )
    return reachable[-1]


def _longest_unique_length(text):
    last_seen = {}
    start = 0
    longest = 0
    for index, character in enumerate(text):
        if character in last_seen and last_seen[character] >= start:
            start = last_seen[character] + 1
        last_seen[character] = index
        longest = max(longest, index - start + 1)
    return longest


def _max_subarray(values):
    current = best = values[0]
    for value in values[1:]:
        current = max(value, current + value)
        best = max(best, current)
    return best


def _top_k(values, amount):
    counts = Counter(values)
    first_seen = {value: index for index, value in reversed(list(enumerate(values)))}
    return sorted(counts, key=lambda value: (-counts[value], first_seen[value]))[:amount]


def _merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return merged


def _shortest_path_length(graph, start, target):
    queue = deque([(start, 0)])
    visited = {start}
    while queue:
        node, distance = queue.popleft()
        if node == target:
            return distance
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    return None


def _even_example(index):
    number = index - 6
    return repr(number), number % 2 == 0


def _factorial_example(index):
    return repr(index), factorial(index)


def _vowel_example(index):
    samples = [
        "python", "Interview", "queueing", "rhythm", "Data science",
        "algorithm", "CODE review", "aeiou", "concurrency", "immutable",
        "generator", "tuple", "edge case",
    ]
    text = samples[index]
    return repr(text), _count_vowels(text)


def _even_squares_example(index):
    values = [index - 7, index % 5 - 2, index + 2, 3 - index]
    result = [value * value for value in values if value % 2 == 0]
    return repr(values), result


def _whitespace_example(index):
    samples = [
        "red   blue", "  alpha beta  ", "one\ttwo", "line\nbreak",
        "multiple \t spaces", "single", "   ", "north\nsouth east",
        "tabs\t\tmerge", "leading\t and trailing ", "a  b   c",
        "return\nvalue", "  Python   interview  ",
    ]
    text = samples[index]
    return repr(text), " ".join(text.split())


def _palindrome_example(index):
    words = [
        "level", "python", "radar", "coding", "civic", "interview",
        "refer", "neveroddoreven", "kayak", "algorithm", "noon",
        "practice", "rotor",
    ]
    word = words[index]
    text = f"{word}!?{word[::-1]}" if index % 2 == 0 else f"{word}!?x"
    return repr(text), _is_palindrome(text)


def _unique_order_example(index):
    values = [index, index + 1, index, index + 2, index + 1, index + 3, index]
    return repr(values), list(dict.fromkeys(values))


def _sum_digits_example(index):
    number = index * 137 + 45
    return repr(number), sum(int(digit) for digit in str(number))


def _first_unique_example(index):
    samples = [
        "swiss", "teeter", "level", "aabbc", "abacabad", "minimum",
        "interview", "success", "alphabet", "mississippi", "bookkeeper",
        "abracadabra", "python",
    ]
    text = samples[index]
    return repr(text), _first_unique(text)


def _brackets_example(index):
    valid_samples = ["()", "([])", "{[()]}", "((()))", "[]{}()", "([{}])", "{}"]
    invalid_samples = [")(", "([)]", "{]", "((", "[}(", "(()", "{}]"]
    text = valid_samples[index // 2] if index % 2 == 0 else invalid_samples[index // 2]
    return repr(text), _balanced_brackets(text)


def _binary_search_example(index):
    values = list(range(-12, 14, 2))
    target = index - 6
    result = values.index(target) if target in values else -1
    return f"{values!r}, {target}", result


def _missing_number_example(index):
    upper = index + 2
    missing = (index * 3) % upper + 1
    values = [number for number in range(1, upper + 1) if number != missing]
    return repr(values), missing


def _most_frequent_example(index):
    values = [index, index + 1, index, index + 2, index + 1, index]
    return repr(values), _most_frequent(values)


def _rotate_example(index):
    values = list(range(index, index + 5))
    amount = index % 8
    return f"{values!r}, {amount}", _rotate_right(values, amount)


def _two_sum_example(index):
    values = [index, 5, index + 11, -50]
    target = index + 5
    return f"{values!r}, {target}", _two_sum(values, target)


def _merge_sorted_example(index):
    left = [index - 8, index - 3, index + 5]
    right = [index - 7, index, index + 2]
    return f"{left!r}, {right!r}", sorted(left + right)


def _profit_example(index):
    prices = [index + value for value in [9, 4, 7, 2, 11, 5]]
    return repr(prices), _max_profit(prices)


def _change_example(index):
    coin_sets = [[1, 2, 5], [1, 3, 4], [2, 3], [1, 4, 6], [2, 5, 7]]
    coins = coin_sets[index % len(coin_sets)]
    amount = index + 3
    return f"{coins!r}, {amount}", _count_change(coins, amount)


def _word_break_example(index):
    text = f"python{index}" if index % 2 == 0 else f"pythonx{index}"
    words = {"py", "thon", "python", f"{index}"}
    # Sorted set literal: a set repr follows the per-process hash seed, and the
    # prompt is an identity field (ADR-005), so it must be identical on every start.
    words_literal = "{" + ", ".join(repr(word) for word in sorted(words)) + "}"
    return f"{text!r}, {words_literal}", _can_segment(text, words)


def _longest_unique_example(index):
    samples = [
        "abcabcbb", "bbbbb", "pwwkew", "interview", "dvdf", "anviaj",
        "tmmzuxt", "coding", "algorithm", "abcaef", "aAbBcC", "mississippi",
        "unique_window",
    ]
    text = samples[index]
    return repr(text), _longest_unique_length(text)


def _subarray_example(index):
    values = [index - 6, -2, 7 - index, 4, -(index % 4 + 1)]
    return repr(values), _max_subarray(values)


def _top_k_example(index):
    values = [index, index, index + 1, index + 2, index + 1, index + 3, index]
    amount = 3
    return f"{values!r}, {amount}", _top_k(values, amount)


def _intervals_example(index):
    intervals = [
        [index + 5, index + 7],
        [index, index + 2],
        [index + 2, index + 4],
        [index + 10, index + 11],
    ]
    return repr(intervals), _merge_intervals(intervals)


def _path_example(index):
    offset = index * 10
    graph = {
        offset: [offset + 1, offset + 2],
        offset + 1: [offset + 3],
        offset + 2: [offset + 3],
        offset + 3: [] if index % 3 == 0 else [offset + 4],
        offset + 4: [],
    }
    target = offset + 4
    result = _shortest_path_length(graph, offset, target)
    return f"{graph!r}, {offset}, {target}", result


CODING_ARCHETYPES = [
    {
        "name": "is_even",
        "topic": "Python Core",
        "difficulty": "Foundations",
        "prompt": "Write is_even(number), returning True when the integer is even and False otherwise.",
        "starter_code": "def is_even(number: int) -> bool:\n    pass",
        "criteria": [
            {"label": "Uses remainder or parity", "keywords": ["% 2", "even", "parity"]},
            {"label": "Returns a boolean result", "keywords": ["return", "bool", "true", "false"]},
            {"label": "Handles zero and negative integers", "keywords": ["zero", "negative", "% 2"]},
        ],
        "explanation": "An integer is even exactly when its remainder after division by two is zero. Python's modulo operation works consistently for negative integers too, so one expression covers positive, zero, and negative inputs.",
        "solution": "def is_even(number: int) -> bool:\n    return number % 2 == 0",
        "example": _even_example,
    },
    {
        "name": "factorial",
        "topic": "Python Core",
        "difficulty": "Foundations",
        "prompt": "Write factorial(number) for a non-negative integer. Define 0! as 1.",
        "starter_code": "def factorial(number: int) -> int:\n    pass",
        "criteria": [
            {"label": "Uses the multiplicative definition", "keywords": ["multiply", "product", "factorial"]},
            {"label": "Has the zero base case", "keywords": ["zero", "1", "base case"]},
            {"label": "Returns an integer result", "keywords": ["return", "range(", "integer"]},
        ],
        "explanation": "The factorial is the product of integers from one through n, with the empty product 0! defined as one. An iterative loop starts with result one and multiplies each factor, using O(n) time and O(1) extra space.",
        "solution": "def factorial(number: int) -> int:\n    result = 1\n    for factor in range(2, number + 1):\n        result *= factor\n    return result",
        "example": _factorial_example,
    },
    {
        "name": "count_vowels",
        "topic": "Python Core",
        "difficulty": "Foundations",
        "prompt": "Write count_vowels(text), counting the English vowels a, e, i, o, and u without regard to case.",
        "starter_code": "def count_vowels(text: str) -> int:\n    pass",
        "criteria": [
            {"label": "Checks only the five vowels", "keywords": ["aeiou", "vowels", "in "]},
            {"label": "Counts case-insensitively", "keywords": ["lower(", "casefold(", "case-insensitive"]},
            {"label": "Accumulates and returns a count", "keywords": ["sum(", "count", "return"]},
        ],
        "explanation": "Scan the string once and increment the result for characters in the vowel set. Normalize each character or the input once to make the check case-insensitive. The algorithm is O(n) time and O(1) extra space.",
        "solution": "def count_vowels(text: str) -> int:\n    return sum(character.casefold() in 'aeiou' for character in text)",
        "example": _vowel_example,
    },
    {
        "name": "even_squares",
        "topic": "Data Structures",
        "difficulty": "Foundations",
        "prompt": "Write even_squares(values), returning the squares of even integers in encounter order without changing the input.",
        "starter_code": "def even_squares(values: list[int]) -> list[int]:\n    pass",
        "criteria": [
            {"label": "Filters even values", "keywords": ["% 2", "even", "if "]},
            {"label": "Squares each selected value", "keywords": ["** 2", "* value", "square"]},
            {"label": "Builds a new ordered list", "keywords": ["list comprehension", "for value", "append", "return"]},
        ],
        "explanation": "A list comprehension performs a filter and mapping in one pass. It preserves input order and creates a new list, leaving the original untouched. Time and output space are O(n).",
        "solution": "def even_squares(values: list[int]) -> list[int]:\n    return [value ** 2 for value in values if value % 2 == 0]",
        "example": _even_squares_example,
    },
    {
        "name": "normalize_whitespace",
        "topic": "Python Core",
        "difficulty": "Foundations",
        "prompt": "Write normalize_whitespace(text), collapsing whitespace runs to one space and trimming the ends.",
        "starter_code": "def normalize_whitespace(text: str) -> str:\n    pass",
        "criteria": [
            {"label": "Uses whitespace-aware splitting", "keywords": ["split()", "split(", "whitespace"]},
            {"label": "Joins with one space", "keywords": ["join(", "' '.join", "\" \".join"]},
            {"label": "Handles empty or whitespace-only text", "keywords": ["empty", "split", "''", "\"\""]},
        ],
        "explanation": "Calling split without an explicit separator treats consecutive whitespace as one delimiter and discards leading and trailing whitespace. Joining with a single space normalizes the result; whitespace-only input becomes an empty string.",
        "solution": "def normalize_whitespace(text: str) -> str:\n    return ' '.join(text.split())",
        "example": _whitespace_example,
    },
    {
        "name": "is_palindrome",
        "topic": "Data Structures",
        "difficulty": "Foundations",
        "prompt": "Write is_palindrome(text), ignoring case and non-alphanumeric characters. The empty normalized string counts as a palindrome.",
        "starter_code": "def is_palindrome(text: str) -> bool:\n    pass",
        "criteria": [
            {"label": "Normalizes case and filters characters", "keywords": ["casefold", "lower(", "isalnum", "alphanumeric"]},
            {"label": "Compares with a reverse or two-pointer scan", "keywords": ["[::-1]", "reverse", "two pointer", "two-pointer"]},
            {"label": "Handles empty normalized input", "keywords": ["empty", "''", "\"\"", "true"]},
        ],
        "explanation": "Normalize by retaining alphanumeric characters and applying case folding, then compare the result to its reverse. The empty normalized string equals its reverse. This direct approach uses O(n) time and O(n) extra space.",
        "solution": "def is_palindrome(text: str) -> bool:\n    normalized = ''.join(char.casefold() for char in text if char.isalnum())\n    return normalized == normalized[::-1]",
        "example": _palindrome_example,
    },
    {
        "name": "unique_in_order",
        "topic": "Data Structures",
        "difficulty": "Foundations",
        "prompt": "Write unique_in_order(values), removing repeated values while preserving the first occurrence order.",
        "starter_code": "def unique_in_order(values: list[int]) -> list[int]:\n    pass",
        "criteria": [
            {"label": "Tracks values already seen", "keywords": ["seen", "set(", "dict.fromkeys"]},
            {"label": "Keeps first-seen order", "keywords": ["order", "append", "dict.fromkeys"]},
            {"label": "Returns a new collection", "keywords": ["return", "result", "list"]},
        ],
        "explanation": "Maintain a set of values already encountered and append only unseen values to a result list. This preserves the original order and takes O(n) expected time with O(k) extra space. For hashable values, dict.fromkeys is a concise alternative on modern Python.",
        "solution": "def unique_in_order(values):\n    seen = set()\n    result = []\n    for value in values:\n        if value not in seen:\n            seen.add(value)\n            result.append(value)\n    return result",
        "example": _unique_order_example,
    },
    {
        "name": "sum_digits",
        "topic": "Python Core",
        "difficulty": "Foundations",
        "prompt": "Write sum_digits(number) for a non-negative integer, returning the sum of its decimal digits.",
        "starter_code": "def sum_digits(number: int) -> int:\n    pass",
        "criteria": [
            {"label": "Visits each decimal digit", "keywords": ["str(", "while", "% 10"]},
            {"label": "Converts digits to integers", "keywords": ["int(", "digit"]},
            {"label": "Accumulates a total", "keywords": ["sum", "+=", "return"]},
        ],
        "explanation": "Convert the non-negative integer to its decimal representation and sum the integer value of each character. This simple approach is O(d) time and space for d digits. A numeric loop using modulo and floor division can avoid the string allocation.",
        "solution": "def sum_digits(number: int) -> int:\n    return sum(int(digit) for digit in str(number))",
        "example": _sum_digits_example,
    },
    {
        "name": "first_unique",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write first_unique(text), returning the first character that occurs once, or None if there is no such character.",
        "starter_code": "def first_unique(text: str) -> str | None:\n    pass",
        "criteria": [
            {"label": "Counts character frequencies", "keywords": ["counter", "count", "frequency"]},
            {"label": "Scans original order", "keywords": ["for char", "for character", "for item"]},
            {"label": "Returns None when absent", "keywords": ["none", "return none"]},
        ],
        "explanation": "Count each character, then scan the original string from left to right and return the first with frequency one. Counting and scanning are both O(n), with O(k) extra space for k distinct characters.",
        "solution": "from collections import Counter\n\ndef first_unique(text: str) -> str | None:\n    counts = Counter(text)\n    return next((char for char in text if counts[char] == 1), None)",
        "example": _first_unique_example,
    },
    {
        "name": "balanced_brackets",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write balanced_brackets(text) for (), [], and {}. Return False for a mismatched or unclosed bracket.",
        "starter_code": "def balanced_brackets(text: str) -> bool:\n    pass",
        "criteria": [
            {"label": "Uses a stack", "keywords": ["stack", "append(", "pop("]},
            {"label": "Validates matching bracket types", "keywords": ["pairs", "mapping", "match", "=="]},
            {"label": "Rejects early or leftover closes", "keywords": ["empty", "not stack", "return false", "return not stack"]},
        ],
        "explanation": "The last unclosed opener must match the next closer, so a stack models the nesting order. Reject a closer when the stack is empty or has a different opener, and require the stack to be empty at the end. The scan is O(n) time and O(n) space.",
        "solution": "def balanced_brackets(text: str) -> bool:\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n    for char in text:\n        if char in '([{':\n            stack.append(char)\n        elif char in pairs:\n            if not stack or stack.pop() != pairs[char]:\n                return False\n    return not stack",
        "example": _brackets_example,
    },
    {
        "name": "binary_search",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write binary_search(values, target) for ascending sorted integers. Return a matching index or -1.",
        "starter_code": "def binary_search(values: list[int], target: int) -> int:\n    pass",
        "criteria": [
            {"label": "Maintains search bounds", "keywords": ["left", "right", "low", "high"]},
            {"label": "Halves the range at the midpoint", "keywords": ["mid", "middle", "// 2"]},
            {"label": "Returns -1 for a missing target", "keywords": ["return -1", "while left <= right", "while low <= high"]},
        ],
        "explanation": "A comparison at the midpoint eliminates half of the remaining sorted range. Keep inclusive left and right bounds and move one bound past the midpoint. The algorithm takes O(log n) time and O(1) extra space.",
        "solution": "def binary_search(values, target):\n    left, right = 0, len(values) - 1\n    while left <= right:\n        middle = (left + right) // 2\n        if values[middle] == target:\n            return middle\n        if values[middle] < target:\n            left = middle + 1\n        else:\n            right = middle - 1\n    return -1",
        "example": _binary_search_example,
    },
    {
        "name": "missing_number",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write missing_number(values) for distinct integers from 1 through n with exactly one missing value.",
        "starter_code": "def missing_number(values: list[int]) -> int:\n    pass",
        "criteria": [
            {"label": "Derives n from the list length", "keywords": ["len(", "length", "n ="]},
            {"label": "Compares expected and actual totals", "keywords": ["sum(", "expected", "actual", "arithmetic"]},
            {"label": "Returns the missing value", "keywords": ["return", "missing", "n + 1"]},
        ],
        "explanation": "The full range ends at n = len(values) + 1. Subtract the observed sum from n(n+1)/2 to get the missing value. This relies on the stated uniqueness and range constraints and runs in O(n) time with O(1) extra space.",
        "solution": "def missing_number(values):\n    n = len(values) + 1\n    return n * (n + 1) // 2 - sum(values)",
        "example": _missing_number_example,
    },
    {
        "name": "most_frequent",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write most_frequent(values), returning the most common item. Break ties by first appearance; return None for an empty list.",
        "starter_code": "def most_frequent(values: list[int]) -> int | None:\n    pass",
        "criteria": [
            {"label": "Counts values", "keywords": ["counter", "count", "frequency"]},
            {"label": "Preserves first-seen tie order", "keywords": ["first", "order", "insertion", "max("]},
            {"label": "Handles empty input", "keywords": ["none", "not values", "if not"]},
        ],
        "explanation": "Count items with Counter, then choose the key with the highest count. Counter preserves insertion order, so max returns the first-seen key when counts tie. Check for empty input first. Expected time is O(n), with O(k) space for k distinct values.",
        "solution": "from collections import Counter\n\ndef most_frequent(values):\n    counts = Counter(values)\n    return max(counts, key=counts.get) if counts else None",
        "example": _most_frequent_example,
    },
    {
        "name": "rotate_right",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write rotate_right(values, amount), returning a right-rotated copy. Amount may exceed the list length; empty input returns an empty list.",
        "starter_code": "def rotate_right(values: list[int], amount: int) -> list[int]:\n    pass",
        "criteria": [
            {"label": "Reduces rotation modulo list length", "keywords": ["% len", "modulo", "%="]},
            {"label": "Handles empty lists", "keywords": ["empty", "if not values", "if not"]},
            {"label": "Moves the suffix to the front", "keywords": ["values[-", "slice", "concatenate", "+"]},
        ],
        "explanation": "Only amount modulo the list length matters. Split at len(values) - amount and concatenate the suffix before the prefix. Handle an empty list before taking a modulo. Slicing creates a new list in O(n) time and space.",
        "solution": "def rotate_right(values, amount):\n    if not values:\n        return []\n    amount %= len(values)\n    return values[-amount:] + values[:-amount] if amount else values[:]",
        "example": _rotate_example,
    },
    {
        "name": "two_sum",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write two_sum(values, target), returning indices of two distinct items whose values add to target, or None if no pair exists.",
        "starter_code": "def two_sum(values: list[int], target: int) -> list[int] | None:\n    pass",
        "criteria": [
            {"label": "Looks up complements", "keywords": ["complement", "target -", "target-"]},
            {"label": "Uses a map for prior values", "keywords": ["seen", "dictionary", "{}", "hash map"]},
            {"label": "Returns distinct indices or None", "keywords": ["index", "none", "return"]},
        ],
        "explanation": "For each value, its needed partner is target - value. Store prior values with their indices so each lookup is O(1) on average. Check for a complement before adding the current item, ensuring an element is not paired with itself. Overall expected time is O(n) and space is O(n).",
        "solution": "def two_sum(values, target):\n    seen = {}\n    for index, value in enumerate(values):\n        complement = target - value\n        if complement in seen:\n            return [seen[complement], index]\n        seen[value] = index\n    return None",
        "example": _two_sum_example,
    },
    {
        "name": "merge_sorted",
        "topic": "Data Structures",
        "difficulty": "Intermediate",
        "prompt": "Write merge_sorted(left, right) for two ascending integer lists. Return one ascending list containing all values.",
        "starter_code": "def merge_sorted(left: list[int], right: list[int]) -> list[int]:\n    pass",
        "criteria": [
            {"label": "Uses two advancing indices", "keywords": ["left_index", "right_index", "i, j", "two pointer"]},
            {"label": "Chooses the smaller next value", "keywords": ["<=", "compare", "smaller"]},
            {"label": "Appends remaining values", "keywords": ["extend(", "remaining", "while"]},
        ],
        "explanation": "A two-pointer merge compares the next unused value from each sorted input and appends the smaller one. Once one input is exhausted, append the remainder of the other. This is O(n + m) time and O(n + m) output space.",
        "solution": "def merge_sorted(left, right):\n    result = []\n    left_index = right_index = 0\n    while left_index < len(left) and right_index < len(right):\n        if left[left_index] <= right[right_index]:\n            result.append(left[left_index])\n            left_index += 1\n        else:\n            result.append(right[right_index])\n            right_index += 1\n    result.extend(left[left_index:])\n    result.extend(right[right_index:])\n    return result",
        "example": _merge_sorted_example,
    },
    {
        "name": "max_single_trade_profit",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write max_single_trade_profit(prices), returning the best profit from one buy followed by a later sell, or zero when no trade profits.",
        "starter_code": "def max_single_trade_profit(prices: list[int]) -> int:\n    pass",
        "criteria": [
            {"label": "Tracks the lowest earlier price", "keywords": ["minimum", "min_price", "lowest", "buy"]},
            {"label": "Computes profit before updating the minimum", "keywords": ["price -", "profit", "sell"]},
            {"label": "Handles short or declining input", "keywords": ["zero", "max(0", "empty", "len("]},
        ],
        "explanation": "At each day, subtract the lowest earlier price from the current price to calculate the best sale available today. Update the running minimum after checking profit. Return zero when fewer than two prices exist or no positive trade exists. Time is O(n); extra space is O(1).",
        "solution": "def max_single_trade_profit(prices):\n    lowest = float('inf')\n    best = 0\n    for price in prices:\n        best = max(best, price - lowest)\n        lowest = min(lowest, price)\n    return best",
        "example": _profit_example,
    },
    {
        "name": "count_change",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write count_change(coins, amount), counting unordered combinations using distinct positive denominations with unlimited reuse.",
        "starter_code": "def count_change(coins: list[int], amount: int) -> int:\n    pass",
        "criteria": [
            {"label": "Uses a one-dimensional ways table", "keywords": ["ways =", "dp =", "amount + 1", "dynamic programming"]},
            {"label": "Initializes one way to make zero", "keywords": ["ways[0] = 1", "dp[0] = 1", "zero amount"]},
            {"label": "Processes each coin before ascending totals", "keywords": ["for coin", "range(coin", "combinations"]},
        ],
        "explanation": "Let ways[a] count combinations that make amount a. There is one way to make zero: choose no coins. For each denomination, update totals upward using ways[a - coin]. Keeping denominations in the outer loop counts combinations rather than different orderings. Complexity is O(coins × amount) time and O(amount) space.",
        "solution": "def count_change(coins, amount):\n    ways = [0] * (amount + 1)\n    ways[0] = 1\n    for coin in coins:\n        for subtotal in range(coin, amount + 1):\n            ways[subtotal] += ways[subtotal - coin]\n    return ways[amount]",
        "example": _change_example,
    },
    {
        "name": "can_segment",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write can_segment(text, words), returning whether the string can be split into dictionary words. The empty string is segmentable.",
        "starter_code": "def can_segment(text: str, words: set[str]) -> bool:\n    pass",
        "criteria": [
            {"label": "Uses prefix reachability or memoized subproblems", "keywords": ["reachable", "dp", "memo", "dynamic programming"]},
            {"label": "Checks candidate word boundaries", "keywords": ["substring", "text[start:end]", "prefix", "boundary"]},
            {"label": "Handles the empty-string base case", "keywords": ["empty", "reachable[0]", "true", "base case"]},
        ],
        "explanation": "Define reachable[i] to mean the prefix ending before i can be segmented. Start with reachable[0] = True. For each end boundary, look for a prior reachable boundary whose intervening substring is a word. The final state answers the question. This straightforward dynamic program uses O(n) states and O(n²) candidate substrings.",
        "solution": "def can_segment(text, words):\n    reachable = [False] * (len(text) + 1)\n    reachable[0] = True\n    for end in range(1, len(text) + 1):\n        for start in range(end):\n            if reachable[start] and text[start:end] in words:\n                reachable[end] = True\n                break\n    return reachable[-1]",
        "example": _word_break_example,
    },
    {
        "name": "longest_unique_substring",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write longest_unique_substring(text), returning the length of the longest substring with no repeated characters.",
        "starter_code": "def longest_unique_substring(text: str) -> int:\n    pass",
        "criteria": [
            {"label": "Uses a sliding window", "keywords": ["window", "start", "left"]},
            {"label": "Tracks previous character positions", "keywords": ["last_seen", "index", "position"]},
            {"label": "Moves the left boundary past duplicates", "keywords": ["max(", "+ 1", "duplicate"]},
        ],
        "explanation": "Maintain a window with unique characters and a map from each character to its latest index. When a repeated character falls inside the window, move the left boundary just past its previous occurrence. Each character is processed once, for O(n) time and O(k) space.",
        "solution": "def longest_unique_substring(text):\n    last_seen = {}\n    start = longest = 0\n    for index, char in enumerate(text):\n        if char in last_seen and last_seen[char] >= start:\n            start = last_seen[char] + 1\n        last_seen[char] = index\n        longest = max(longest, index - start + 1)\n    return longest",
        "example": _longest_unique_example,
    },
    {
        "name": "max_subarray_sum",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write max_subarray_sum(values) for a non-empty integer list, returning the largest sum of a contiguous, non-empty subarray.",
        "starter_code": "def max_subarray_sum(values: list[int]) -> int:\n    pass",
        "criteria": [
            {"label": "Tracks best subarray ending here", "keywords": ["current", "ending", "max("]},
            {"label": "Chooses restart or extension", "keywords": ["current +", "restart", "value"]},
            {"label": "Handles all-negative arrays", "keywords": ["values[0]", "all negative", "non-empty"]},
        ],
        "explanation": "Kadane's algorithm records the best sum ending at each position: either start a new subarray at the current value or extend the previous one. Track the best value seen overall. Initializing from the first item, rather than zero, handles all-negative input. Time is O(n), space O(1).",
        "solution": "def max_subarray_sum(values):\n    current = best = values[0]\n    for value in values[1:]:\n        current = max(value, current + value)\n        best = max(best, current)\n    return best",
        "example": _subarray_example,
    },
    {
        "name": "top_k_frequent",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write top_k_frequent(values, k), returning k values ordered by decreasing frequency, breaking ties by first appearance.",
        "starter_code": "def top_k_frequent(values: list[int], k: int) -> list[int]:\n    pass",
        "criteria": [
            {"label": "Counts occurrences", "keywords": ["counter", "count", "frequency"]},
            {"label": "Defines deterministic tie order", "keywords": ["first", "stable", "order", "tie"]},
            {"label": "Returns exactly k values", "keywords": ["[:k]", "k values"]},
        ],
        "explanation": "Count each value, then sort distinct values by descending count and first-seen position. Explicitly encoding the tie-break makes output deterministic. This simple implementation is O(n + u log u) for u distinct values, with O(u) extra space.",
        "solution": "from collections import Counter\n\ndef top_k_frequent(values, k):\n    counts = Counter(values)\n    first_seen = {value: index for index, value in reversed(list(enumerate(values)))}\n    return sorted(counts, key=lambda value: (-counts[value], first_seen[value]))[:k]",
        "example": _top_k_example,
    },
    {
        "name": "merge_intervals",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write merge_intervals(intervals), combining overlapping inclusive integer intervals and returning the result sorted by start.",
        "starter_code": "def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:\n    pass",
        "criteria": [
            {"label": "Sorts by interval start", "keywords": ["sorted(", "sort(", "start"]},
            {"label": "Compares each start with the last merged end", "keywords": ["merged[-1]", "end", "overlap"]},
            {"label": "Extends the current interval or starts a new one", "keywords": ["append(", "max(", "merge"]},
        ],
        "explanation": "Sort intervals by start, then scan once. If the next interval begins at or before the end of the last merged interval, extend that end; otherwise append a new interval. Because intervals are inclusive, sharing an endpoint counts as overlap. Complexity is O(n log n) time due to sorting and O(n) output space.",
        "solution": "def merge_intervals(intervals):\n    merged = []\n    for start, end in sorted(intervals):\n        if not merged or start > merged[-1][1]:\n            merged.append([start, end])\n        else:\n            merged[-1][1] = max(merged[-1][1], end)\n    return merged",
        "example": _intervals_example,
    },
    {
        "name": "shortest_path_length",
        "topic": "Data Structures",
        "difficulty": "Advanced",
        "prompt": "Write shortest_path_length(graph, start, target) for an unweighted directed graph. Return the edge count or None if unreachable.",
        "starter_code": "def shortest_path_length(graph: dict[int, list[int]], start: int, target: int) -> int | None:\n    pass",
        "criteria": [
            {"label": "Uses breadth-first search", "keywords": ["bfs", "breadth", "deque", "queue"]},
            {"label": "Marks visited nodes", "keywords": ["visited", "seen"]},
            {"label": "Tracks distances and handles unreachable targets", "keywords": ["distance", "none", "target"]},
        ],
        "explanation": "Breadth-first search explores nodes by increasing distance, so the first visit to the target gives the shortest path length in an unweighted graph. Use a queue and visited set to avoid repeated work. Return None if the queue empties first. Time is O(V + E) and space O(V).",
        "solution": "from collections import deque\n\ndef shortest_path_length(graph, start, target):\n    queue = deque([(start, 0)])\n    visited = {start}\n    while queue:\n        node, distance = queue.popleft()\n        if node == target:\n            return distance\n        for neighbor in graph.get(node, []):\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append((neighbor, distance + 1))\n    return None",
        "example": _path_example,
    },
]


def build_coding_variants():
    questions = []
    for archetype in CODING_ARCHETYPES:
        for variant_index in range(VARIATIONS_PER_ARCHETYPE):
            arguments, expected = archetype["example"](variant_index)
            prompt = (
                f"{archetype['prompt']}\n\n"
                f"Example: {archetype['name']}({arguments}) -> {expected!r}"
            )
            questions.append(
                {
                    "topic": archetype["topic"],
                    "difficulty": archetype["difficulty"],
                    "mode": "Coding",
                    "prompt": prompt,
                    "criteria": archetype["criteria"],
                    "explanation": archetype["explanation"],
                    "solution": archetype["solution"],
                    "starter_code": archetype["starter_code"],
                }
            )
    return questions