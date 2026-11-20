#include <iostream>
using namespace std;

int main() {
    int n = 10, result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;
    }
    cout << n << "! = " << result << endl;

    int a = 7, b = 2;
    double c = 7.0;
    cout << a / b << endl;      // integer division -> 3
    cout << c / b << endl;      // 3.5
    cout << a % b << endl;      // 1
    return 0;
}
