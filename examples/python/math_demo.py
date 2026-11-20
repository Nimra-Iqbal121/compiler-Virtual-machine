# Python arithmetic: / is always float, // floors, ** is power
print(7 / 2, 4 / 2)
print(7 // 2, -7 // 2)
print(7 % 3, -7 % 3)
print(2 ** 10, 2 ** -1)

n = 10
result = 1
for i in range(2, n + 1):
    result *= i
print(f"{n}! = {result}")

a, b = 3, 8
a, b = b, a
print(a, b)
print(1 < 2 < 3, 0 or "default", not True)
print(max(4, 9), min(4, 9), abs(-5), round(2.5), int("40") + 2)
