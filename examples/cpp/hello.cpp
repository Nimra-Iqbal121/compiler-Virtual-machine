#include <iostream>
#include <string>
using namespace std;

int main() {
    string name = "Ali";
    int year = 2026;
    cout << "Hello, " << name << "!" << endl;
    cout << "Year: " << year << endl;
    cout << "Next: " + to_string(year + 1) << endl;
    return 0;
}
