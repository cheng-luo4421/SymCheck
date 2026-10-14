"""Independent classical RK4 reference; no SciPy integrator is used."""
import argparse
import json
import math
import platform
import time
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

ANALYTIC = '(5*exp(-2*t) + 2*t - 1)/4'

def dependency_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return 'not-installed (not required by this standalone experiment)'

def rhs(t, y):
    return -2.0*y+t

def rk4(h):
    t, y = 0.0, 1.0
    for _ in range(round(1.0/h)):
        k1 = rhs(t, y)
        k2 = rhs(t+h/2, y+h*k1/2)
        k3 = rhs(t+h/2, y+h*k2/2)
        k4 = rhs(t+h, y+h*k3)
        y += h*(k1+2*k2+2*k3+k4)/6
        t += h
    return y

def run():
    start = time.perf_counter()
    exact = (5*math.exp(-2)+1)/4
    steps = []
    for h in (0.1, 0.05, 0.025, 0.0125):
        value = rk4(h)
        steps.append({'h': h, 'y_h': value, 'e_h': abs(value-exact)})
    ratios = [a['e_h']/b['e_h'] for a,b in zip(steps,steps[1:])]
    result = {'id': 'rk4-bonus', 'analytic': ANALYTIC, 'y_exact_at_1': exact,
              'steps': steps, 'ratios': ratios,
              'observed_order': sum(map(math.log2, ratios))/3,
              'python': platform.python_version(), 'sympy': dependency_version('sympy'),
              'scipy': dependency_version('scipy')}
    result['runtime_s'] = time.perf_counter()-start
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='rk4_out.json')
    args = parser.parse_args()
    result = run()
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
