public class Factorial {
    public static void main(String[] args) {
        int n = 10;
        int result = 1;
        int i = 1;
        while (i <= n) {
            result = result * i;
            i++;
        }
        System.out.println(n + "! = " + result);
        System.out.println(7 / 2);        // 3
        System.out.println(7 / 2.0);      // 3.5
        System.out.print("no newline, ");
        System.out.println("then newline");
    }
}
