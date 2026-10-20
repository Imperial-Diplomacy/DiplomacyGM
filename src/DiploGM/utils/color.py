import random as rng
from math import sqrt, atan2, pi

def lineartogamma(val: float) -> float:
    return 1.055 * val**(1/2.4) - 0.055 if val >= 0.0031308 else 12.92 * val

def clamp(minval: int, val: float, maxval: int) -> int:
    return int(min(max(minval, int(val)), maxval))

def oklab_random() -> str:
    L = max(rng.random()*0.8 + 0.2, 0.3)
    a = rng.random()*0.8 - 0.4
    b = rng.random()*0.8 - 0.4

    l = L + a* 0.3963377774 + b* 0.2158037573
    m = L + a*-0.1055613458 + b*-0.0638541728
    s = L + a*-0.0894841775 + b*-1.2914855480

    l, m, s = l**3, m**3, s**3

    r = l* 4.0767416621 + m*-3.3077115913 + s* 0.2309699292
    g = l*-1.2684380046 + m* 2.6097574011 + s*-0.3413193965
    b = l*-0.0041960863 + m*-0.7034186147 + s* 1.7076147010

    r, g, b = round(255*lineartogamma(r)), round(255*lineartogamma(g)), round(255*lineartogamma(b))
    #r, g, b = round(255*r), round(255*g), round(255*b)

    r, g, b = clamp(0, r, 255), clamp(0, g, 255), clamp(0, b, 255)

    hex = f"{r:02x}{g:02x}{b:02x}"

    return hex
