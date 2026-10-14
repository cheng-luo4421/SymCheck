"""SymCheck 评测数据：15 道基础题与 1 道 RK4 加分题。

expr 为未求值的 SymPy 对象；expected 为可解析的标准答案字符串。
threshold 为绝对误差阈值。vars 按未知量/自变量顺序列出名称。
不定积分答案省略任意加法常数，判定时应允许相差常数。
ODE 通解中 C1、C2 为任意实常数，允许等价的常数重参数化。
特征向量允许任意非零倍数；参考答案按特征值升序给出单位向量。
本模块仅声明数据，不包含求解、验证或 RK4 实现。
"""

from sympy import (
    Derivative, Eq, Function, Integral, Limit, Matrix,
    cos, exp, log, sin, symbols,
)

x, t = symbols("x t", real=True)
u, v, w = symbols("u v w", real=True)
y = Function("y")

SYMBENCH15: list[dict] = [
    {
        "id": "calculus-01", "category": "calculus",
        "statement": "求不定积分 ∫sin(x)·cos(x) dx，x 为实数，答案包含任意常数 C。",
        "expr": Integral(sin(x)*cos(x), x), "vars": ["x"],
        "expected": "sin(x)**2/2", "threshold": 1e-8,
    },
    {
        "id": "calculus-02", "category": "calculus",
        "statement": "求不定积分 ∫x·eˣ dx，x 为实数，答案包含任意常数 C。",
        "expr": Integral(x*exp(x), x), "vars": ["x"],
        "expected": "(x - 1)*exp(x)", "threshold": 1e-8,
    },
    {
        "id": "calculus-03", "category": "calculus",
        "statement": "求不定积分 ∫x²·ln(x) dx，定义域 x>0，答案包含任意常数 C。",
        "expr": Integral(x**2*log(x), x), "vars": ["x"],
        "domain": "x > 0",
        "expected": "x**3*log(x)/3 - x**3/9", "threshold": 1e-8,
    },
    {
        "id": "calculus-04", "category": "calculus",
        "statement": "计算定积分 ∫₀¹ x·exp(x) dx。",
        "expr": Integral(x*exp(x), (x, 0, 1)), "vars": ["x"],
        "expected": "1", "threshold": 1e-8,
    },
    {
        "id": "calculus-05", "category": "calculus",
        "statement": "求双侧极限 lim(x→0) (exp(x)-1-x)/x²。",
        "expr": Limit((exp(x)-1-x)/x**2, x, 0, dir="+-"),
        "vars": ["x"], "expected": "1/2", "threshold": 1e-6,
    },
    {
        "id": "linear-algebra-01", "category": "linear_algebra",
        "statement": "解 2×2 线性方程组 2u+v=5，u-v=1；答案按 (u,v) 排列。",
        "expr": [Eq(2*u+v, 5), Eq(u-v, 1)], "vars": ["u", "v"],
        "expected": "(2, 1)", "threshold": 1e-8,
    },
    {
        "id": "linear-algebra-02", "category": "linear_algebra",
        "statement": "解 3×3 线性方程组 u+v+w=6，2u-v+w=3，u+2v-w=2；答案按 (u,v,w) 排列。",
        "expr": [Eq(u+v+w, 6), Eq(2*u-v+w, 3), Eq(u+2*v-w, 2)],
        "vars": ["u", "v", "w"], "expected": "(1, 2, 3)",
        "threshold": 1e-8,
    },
    {
        "id": "linear-algebra-03", "category": "linear_algebra",
        "statement": "求矩阵 A=[[2,1],[1,1]] 的逆矩阵。",
        "expr": Matrix([[2, 1], [1, 1]]), "vars": [],
        "expected": "Matrix([[1, -1], [-1, 2]])", "threshold": 1e-8,
    },
    {
        "id": "linear-algebra-04", "category": "linear_algebra",
        "statement": "求矩阵 A=[[2,1],[1,2]] 的全部特征值及对应特征向量。按特征值升序输出 (特征值,单位列向量)；参考向量首个非零分量为正，等价非零倍数也正确。",
        "expr": Matrix([[2, 1], [1, 2]]), "vars": [],
        "expected": "[(1, Matrix([1/sqrt(2), -1/sqrt(2)])), (3, Matrix([1/sqrt(2), 1/sqrt(2)]))]",
        "threshold": 1e-8,
    },
    {
        "id": "linear-algebra-05", "category": "linear_algebra",
        "statement": "计算矩阵 A=[[1,2,3],[0,1,4],[5,6,0]] 的行列式。",
        "expr": Matrix([[1, 2, 3], [0, 1, 4], [5, 6, 0]]), "vars": [],
        "expected": "1", "threshold": 1e-8,
    },
    {
        "id": "ode-01", "category": "ode",
        "statement": "求一阶可分离变量方程 y'(t)=t·y(t) 的通解，包含零解。",
        "expr": Eq(Derivative(y(t), t), t*y(t)), "vars": ["t"],
        "expected": "C1*exp(t**2/2)", "threshold": 1e-6,
    },
    {
        "id": "ode-02", "category": "ode",
        "statement": "求一阶线性方程 y'(t)+2y(t)=t 的通解。",
        "expr": Eq(Derivative(y(t), t)+2*y(t), t), "vars": ["t"],
        "expected": "C1*exp(-2*t) + t/2 - 1/4", "threshold": 1e-6,
    },
    {
        "id": "ode-03", "category": "ode",
        "statement": "求二阶常系数齐次方程 y''(t)-3y'(t)+2y(t)=0 的通解。",
        "expr": Eq(Derivative(y(t), (t, 2))-3*Derivative(y(t), t)+2*y(t), 0),
        "vars": ["t"], "expected": "C1*exp(t) + C2*exp(2*t)",
        "threshold": 1e-6,
    },
    {
        "id": "ode-04", "category": "ode",
        "statement": "求二阶常系数非齐次方程 y''(t)+y(t)=t 的通解。",
        "expr": Eq(Derivative(y(t), (t, 2))+y(t), t), "vars": ["t"],
        "expected": "C1*cos(t) + C2*sin(t) + t", "threshold": 1e-6,
    },
    {
        "id": "ode-05", "category": "ode",
        "statement": "解初值问题 y''(t)+4y(t)=0，y(0)=1，y'(0)=0。",
        "expr": Eq(Derivative(y(t), (t, 2))+4*y(t), 0), "vars": ["t"],
        "ics": {y(0): 1, Derivative(y(t), t).subs(t, 0): 0},
        "expected": "cos(2*t)", "threshold": 1e-6,
    },
]

RK4_BONUS: dict = {
    "id": "rk4-bonus",
    "category": "ode",
    "statement": "用 RK4 方法数值求解初值问题 dy/dt = -2y + t,y(0) = 1,取步长 h = 0.1、0.05、0.025、0.0125,计算 t=1 处的数值解,并与解析解对比,验证收敛阶为 4",
    "expr": Eq(Derivative(y(t), t), -2*y(t) + t),
    "vars": ["t"],
    "ics": {y(0): 1},
    "expected": "(5*exp(-2*t) + 2*t - 1)/4",
    "threshold": 1e-6,
}
