// break / continue, % and logical operators
let i = 0;
while (true) {
    i = i + 1;
    if (i % 2 == 0) { continue; }
    if (i > 9) { break; }
    print(i);
}
print(i > 5 && !(i == 3));
