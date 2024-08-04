#include <iostream>
#include <cmath>

namespace MathUtils {

    // Function declarations
    double computeSquareRoot(double value);

    namespace Internal {
        int multiply(int a, int b);
    }

    class Calculator {
    public:
        int add(int a, int b);
        int subtract(int a, int b);
    };

}

// Function definitions
double MathUtils::computeSquareRoot(double value) {
    return std::sqrt(value);
}

int MathUtils::Internal::multiply(int a, int b) {
    return a * b;
}

int MathUtils::Calculator::add(int a, int b) {
    return a + b;
}

int MathUtils::Calculator::subtract(int a, int b) {
    return a - b;
}

int main() {
    MathUtils::Calculator calc;
    int sum = calc.add(5, 3);
    std::cout << "Sum: " << sum << std::endl;

    int difference = calc.subtract(5, 3);
    std::cout << "Difference: " << difference << std::endl;

    double sqrtValue = MathUtils::computeSquareRoot(16.0);
    std::cout << "Square root: " << sqrtValue << std::endl;

    int product = MathUtils::Internal::multiply(5, 3);
    std::cout << "Product: " << product << std::endl;

    return 0;
}
