# for / while / break / continue
for i in range(1, 11):
    if i % 2 == 0:
        continue
    if i > 7:
        break
    print(i)

for k in range(10, 0, -3):
    print("countdown", k)

n = 0
while n < 3:
    print(f"n = {n}")
    n += 1
