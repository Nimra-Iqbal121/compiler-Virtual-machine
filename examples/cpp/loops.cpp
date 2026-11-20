#include <iostream>
using namespace std;

int main() {
    // for, while, break, continue, % and &&
    for (int i = 1; i <= 10; i++) {
        if (i % 2 == 0) continue;
        if (i > 7) break;
        cout << i << " ";
    }
    cout << endl;

    int n = 0;
    while (n < 3) {
        cout << "n = " << n << endl;
        n++;
    }
    return 0;
}
