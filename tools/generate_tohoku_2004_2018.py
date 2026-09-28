#!/usr/bin/env python3
"""Generate the reviewed Tohoku 2004--2018 six-subject sample records."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHOOL = "东北大学"
GRAD = "情报科学研究科"
MAJOR = "数学教室"


DATA = {
    2004: {
        "category": "向量解析", "source": "閮2", "type": "极坐标下的偏导数换算",
        "text": "设 $f(x,y)$ 为二元 $C^2$ 函数，并作极坐标代换 $x=r\\sin\\theta,\\ y=r\\cos\\theta$（$r>0$）。用链式法则证明 $f_r,f_\\theta$ 与 $f_x,f_y$ 的关系，并将 $f_x,f_y$ 用 $f_r,f_\\theta$ 表示。",
        "answer": ["$f_r=f_x\\sin\\theta+f_y\\cos\\theta$，$f_\\theta=r f_x\\cos\\theta-r f_y\\sin\\theta$。", "写成矩阵形式后，其行列式为 $-r\\ne0$，因此可逆。", "解得 $f_x=\\sin\\theta\,f_r+(\\cos\\theta/r)f_\\theta$，$f_y=\\cos\\theta\,f_r-(\\sin\\theta/r)f_\\theta$。"],
        "practice": [("若 $x=r\\cos\\theta,y=r\\sin\\theta$，求 $f_r,f_\\theta$。", "$f_r=f_x\\cos\\theta+f_y\\sin\\theta,　f_\\theta=-rf_x\\sin\\theta+rf_y\\cos\\theta$。"), ("对 $f=x^2+y^2$ 验证极坐标链式关系。", "$f=r^2$，故 $f_r=2r,f_\\theta=0$，与链式计算一致。"), ("用极坐标表示 $f_x^2+f_y^2$。", "$f_x^2+f_y^2=f_r^2+r^{-2}f_\\theta^2$。")],
    },
    2005: {
        "category": "微积分", "source": "閮1", "type": "黎曼和与对数渐近",
        "text": "(1) 求 $\\displaystyle\\lim_{n\\to\\infty}\\frac1n\\sum_{k=1}^n\\frac{k}{n}\\log\\frac{k}{n}$。(2) 求 $\\displaystyle\\lim_{n\\to\\infty}\\frac{(1^1 2^2\\cdots n^n)^{1/n^2}}{n^{1/2}}$。",
        "answer": ["(1) 这是 $\\int_0^1x\\log x\,dx$ 的黎曼和；分部积分得 $\\int_0^1x\\log x\,dx=-1/4$。", "(2) 取对数得 $L_n=\\frac1{n^2}\\sum_{k=1}^nk\\log k-\\frac12\\log n$。", "写成 $L_n=\\frac1n\\sum_{k=1}^n(k/n)\\log(k/n)$，由 (1) 得 $L_n\\to-1/4$，故原极限为 $e^{-1/4}$。"],
        "practice": [("求 $\\lim n^{-1}\\sum_{k=1}^n(k/n)^2$。", "极限为 $\\int_0^1x^2dx=1/3$。"), ("求 $\\int_0^1x^2\\log x\,dx$。", "分部积分得 $-1/9$。"), ("求 $\\lim_{n\\to\\infty}(n!)^{1/n}/n$。", "取对数并用黎曼和：$\\frac1n\\sum\\log(k/n)\\to-1$，故为 $e^{-1}$。")],
    },
    2006: {
        "category": "微积分", "source": "閮1(1)", "type": "高斯积分",
        "text": "计算 $\\displaystyle\\int_0^\\infty\\!\\int_0^\\infty e^{-(x^2+y^2)}dxdy$，并由此证明 $\\displaystyle\\int_0^\\infty e^{-x^2}dx=\\sqrt\\pi/2$。",
        "answer": ["积分被积函数非负，可用 Tonelli 定理将二重积分写成 $I^2$，其中 $I=\\int_0^\\infty e^{-x^2}dx$。", "在第一象限作极坐标代换：$dxdy=rdrd\\theta$。因此 $I^2=\\int_0^{\\pi/2}d\\theta\\int_0^\\infty e^{-r^2}rdr=\\frac\\pi2\\cdot\\frac12=\\frac\\pi4$。", "由 $I>0$ 得 $I=\\sqrt\\pi/2$。"],
        "practice": [("计算 $\\int_{\\mathbb R^2}e^{-(x^2+y^2)}dxdy$。", "极坐标下为 $2\\pi\\int_0^\\infty e^{-r^2}rdr=\\pi$。"), ("计算 $\\int_0^\\infty xe^{-x^2}dx$。", "令 $u=x^2$，结果为 $1/2$。"), ("计算 $\\int_0^\\infty e^{-ax^2}dx$（$a>0$）。", "令 $u=\\sqrt a x$，得 $\\sqrt\\pi/(2\\sqrt a)$。")],
    },
    2007: {
        "category": "微积分", "source": "閮1", "type": "条件极值",
        "text": "设 $a,b,c>0$，$E=\\{(x,y,z):x^2/a^2+y^2/b^2+z^2/c^2=1,\\ x,y,z>0\\}$。用拉格朗日乘子法求 $xyz$ 在 $E$ 上的最大值。",
        "answer": ["对 $G=xyz+\\lambda(x^2/a^2+y^2/b^2+z^2/c^2-1)$ 求偏导，得 $yz=-2\\lambda x/a^2$等式。", "分别乘以 $x,y,z$，得 $x^2/a^2=y^2/b^2=z^2/c^2$。再用约束得 $x=a/\\sqrt3,y=b/\\sqrt3,z=c/\\sqrt3$。", "边界上乘积趋于 $0$，而驻点乘积为正，故最大值为 $abc/(3\\sqrt3)$。"],
        "practice": [("在 $x^2+y^2=1,x,y>0$ 上求 $xy$ 的最大值。", "$x=y=1/\\sqrt2$，最大值 $1/2$。"), ("在 $x+y+z=1,x,y,z>0$ 上求 $xyz$ 的最大值。", "由 AM-GM，最大值 $1/27$，在 $x=y=z=1/3$ 取得。"), ("在 $x^2/4+y^2/9=1$ 上求 $|xy|$ 的最大值。", "令 $x=2u,y=3v$，$u^2+v^2=1$，故最大值为 $3$。")],
    },
    2008: {
        "category": "微积分", "source": "閮1", "type": "$p$ 范数单调性",
        "text": "设 $a,b>0$。证明：(1) $x>0,p>1$ 时 $(x+1)^p>x^p+1$；(2) $p>1$ 时 $(a+b)^p>a^p+b^p$；(3) $q>p>0$ 时 $(a^p+b^p)^{1/p}>(a^q+b^q)^{1/q}$；(4) $\\lim_{p\\to\\infty}(a^p+b^p)^{1/p}=\\max\\{a,b\\}$。",
        "answer": ["令 $h(x)=(x+1)^p-x^p-1$，则 $h(0)=0$且 $h'(x)=p[(x+1)^{p-1}-x^{p-1}]>0$，故 (1) 成立；尺度变换立得 (2)。", "令 $A=(a^p+b^p)^{1/p}$，则 $(a/A)^p+(b/A)^p=1$且两项都在 $(0,1)$。因 $q/p>1$，有 $(a/A)^q+(b/A)^q<1$，故 $(a^q+b^q)^{1/q}<A$。", "设 $M=\\max(a,b)$，则 $M\\le(a^p+b^p)^{1/p}\\le2^{1/p}M$，夹逼得极限为 $M$。"],
        "practice": [("证明 $(a^p+b^p)^{1/p}\\le2^{1/p}\\max(a,b)$。", "由 $a^p,b^p\\le M^p$，两边取 $p$ 次方根即得。"), ("求 $\\lim_{p\\to\\infty}(1+3^p+5^p)^{1/p}$。", "最大项夹逼，结果为 $5$。"), ("比较 $(1^2+2^2)^{1/2}$ 与 $(1^4+2^4)^{1/4}$。", "由范数指数单调性，前者较大。")],
    },
    2009: {
        "category": "微积分", "source": "閮1", "type": "可导与导函数连续性",
        "text": "定义 $f(x)=x^2\\cos(1/x)$（$x\\ne0$），$f(0)=0$。(1) 求 $x\\ne0$ 时的导数；(2) 证明 $f$ 在 $0$ 可导；(3) 证明 $f'$ 在 $0$ 不连续；(4) 给出二次可导但二阶导数在 $0$ 不连续的例子。",
        "answer": ["$x\\ne0$ 时 $f'(x)=2x\\cos(1/x)+\\sin(1/x)$。而 $f'(0)=\\lim_{h\\to0}h\\cos(1/h)=0$。", "取 $x_n=1/(\\pi/2+2\\pi n)$ 与 $y_n=1/(3\\pi/2+2\\pi n)$，则 $f'(x_n)\\to1$、$f'(y_n)\\to-1$，因此 $f'$ 在 $0$ 不连续。", "例如 $g(x)=x^4\\cos(1/x)$（$x\\ne0$），$g(0)=0$。可验证 $g''(0)=0$，但 $x\\ne0$ 时 $g''(x)=12x^2\\cos(1/x)+6x\\sin(1/x)-\\cos(1/x)$，在 $0$ 附近无极限。"],
        "practice": [("判断 $x^3\\sin(1/x)$ 在 $0$ 处是否可导。", "差商为 $x^2\\sin(1/x)\\to0$，故可导且导数为 $0$。"), ("判断 $x\\sin(1/x)$ 在 $0$ 处是否可导。", "差商为 $\\sin(1/x)$，无极限，故不可导。"), ("给出可导但导函数在 $0$ 不连续的函数。", "$x^2\\sin(1/x)$（$x\\ne0$）并令 $f(0)=0$ 即可。")],
    },
    2010: {
        "category": "微积分", "source": "閮1", "type": "加权乘积的条件极值",
        "text": "设 $a,b,c>0$。当 $x,y,z>0$ 且 $x^2+y^2+z^2=1$ 时，求 $x^a y^b z^c$ 的最大值。",
        "answer": ["最大化对数 $a\\log x+b\\log y+c\\log z$，并对约束引入乘子 $\\lambda$。", "驻点方程给出 $a/x=2\\lambda x$、$b/y=2\\lambda y$、$c/z=2\\lambda z$，故 $x^2:y^2:z^2=a:b:c$。", "令 $s=a+b+c$，得 $x^2=a/s,y^2=b/s,z^2=c/s$。最大值是 $(a/s)^{a/2}(b/s)^{b/2}(c/s)^{c/2}$。"],
        "practice": [("在 $x^2+y^2=1$ 上最大化 $x^2y^4$（$x,y>0$）。", "$x^2=1/3,y^2=2/3$，最大值 $4/27$。"), ("在 $x+y=1$ 上最大化 $x^a y^b$。", "$x=a/(a+b),y=b/(a+b)$。"), ("在单位球面第一卦限最大化 $xyz$。", "$x=y=z=1/\\sqrt3$，最大值 $1/(3\\sqrt3)$。")],
    },
    2011: {
        "category": "线性代数", "source": "閮1", "type": "正交补空间",
        "text": "在 $\\mathbb R^n$ 中证明：(1) $\\dim W^\\perp=n-\\dim W$；(2) $(W^\\perp)^\\perp=W$；(3) $(W_1+W_2)^\\perp=W_1^\\perp\\cap W_2^\\perp$；(4) $(W_1\\cap W_2)^\\perp=W_1^\\perp+W_2^\\perp$。",
        "answer": ["将 $W$ 的正交基扩张为 $\\mathbb R^n$ 的正交基，新增基向量正好张成 $W^\\perp$，得维数公式。", "$W\\subset(W^\\perp)^\\perp$，两边维数同为 $\\dim W$，故相等。而一个向量同时正交于 $W_1,W_2$ 当且仅当它正交于 $W_1+W_2$，得 (3)。", "对 (3) 中的 $W_1^\\perp,W_2^\\perp$ 再取正交补，并使用双重正交补等式，即得 (4)。"],
        "practice": [("在 $\\mathbb R^3$ 中求 $\\operatorname{span}(1,1,0)^\\perp$。", "$\\{(x,y,z):x+y=0\\}=\\operatorname{span}\\{(1,-1,0),(0,0,1)\\}$。"), ("若 $U\\subset V$，证明 $V^\\perp\\subset U^\\perp$。", "正交于 $V$ 的向量必然正交于其子空间 $U$。"), ("求 $\\dim(W^\\perp)$，已知 $W\\subset\\mathbb R^7$ 且 $\\dim W=3$。", "由维数公式得 $4$。")],
    },
    2012: {
        "category": "线性代数", "source": "閮2", "type": "对称矩阵对角化与半正定性",
        "text": "设 $A=\\begin{pmatrix}a&b&b\\\\b&a&b\\\\b&b&a\\end{pmatrix}$。(1) 用正交矩阵对角化 $A$；(2) 求对任意 $x\\in\\mathbb R^3$ 都有 $x^TAx\\ge0$ 的 $a,b$ 充要条件。",
        "answer": ["向量 $(1,1,1)^T$ 是特征向量，特征值为 $a+2b$。与它正交的平面 $x_1+x_2+x_3=0$ 上 $A$ 等于 $(a-b)I$。", "取正交特征基 $u_1=(1,1,1)/\\sqrt3,u_2=(1,-1,0)/\\sqrt2,u_3=(1,1,-2)/\\sqrt6$，令 $Q=(u_1,u_2,u_3)$，则 $Q^TAQ=\\operatorname{diag}(a+2b,a-b,a-b)$。", "实对称矩阵半正定当且仅当所有特征值非负，故条件为 $a+2b\\ge0$ 且 $a-b\\ge0$。"],
        "practice": [("求 $3\\times3$ 全 $1$ 矩阵的特征值。", "特征值为 $3,0,0$。"), ("判定 $\\begin{pmatrix}2&1&1\\\\1&2&1\\\\1&1&2\\end{pmatrix}$ 是否正定。", "特征值为 $4,1,1$，故正定。"), ("求具有对角元 $a$ 和非对角元 $b$ 的 $n$ 阶矩阵特征值。", "$a+(n-1)b$ 一重，$a-b$ 为 $n-1$ 重。")],
    },
    2013: {
        "category": "线性代数", "source": "閮1", "type": "特征分解与矩阵幂",
        "text": "设 $A$ 是对角元为 $0$、非对角元为非零实数 $a$ 的 $4\\times4$ 对称矩阵，$e=(1,0,0,0)^T$。(1) 求 $A$ 的特征值及重数；(2) 将 $e$ 分解为特征向量之和；(3) 求 $A^ne$。",
        "answer": ["写成 $A=a(J-I)$。$u=(1,1,1,1)^T$ 对应特征值 $3a$，$u^\\perp$ 上特征值为 $-a$，重数 $3$。", "$e=\\frac14u+v$，其中 $v=(3,-1,-1,-1)^T/4\\in u^\\perp$。", "因此 $A^ne=\\frac{(3a)^n}{4}u+\\frac{(-a)^n}{4}(3,-1,-1,-1)^T$。"],
        "practice": [("求 $3\\times3$ 对角为 $0$、非对角为 $1$ 的矩阵特征值。", "$2,-1,-1$。"), ("将 $(1,0,0)^T$ 分解到 $\\operatorname{span}(1,1,1)$ 及其正交补。", "$(1,0,0)=\\frac13(1,1,1)+\\frac13(2,-1,-1)$。"), ("若 $A^2=I$，求 $A^{2025}$。", "$A^{2025}=A$。")],
    },
    2014: {
        "category": "微积分", "source": "閮1", "type": "幂对数函数与反常积分",
        "text": "对实数 $\\alpha$ 令 $f_\\alpha(x)=x^\\alpha\\log x$（$x>0$）。(1) 研究 $f_{-2}$ 的图像；(2) 求 $f_\\alpha$ 的原函数；(3) 求 $\\int_0^1x^\\alpha\\log x\,dx$ 收敛的条件及积分值。",
        "answer": ["$f_{-2}'(x)=x^{-3}(1-2\\log x)$，故在 $x=\\sqrt e$ 取最大值 $1/(2e)$；$f_{-2}''(x)=x^{-4}(6\\log x-5)$，拐点在 $x=e^{5/6}$。", "$\\alpha\\ne-1$ 时，原函数为 $x^{\\alpha+1}[\\log x/(\\alpha+1)-1/(\\alpha+1)^2]+C$；$\\alpha=-1$ 时为 $(\\log x)^2/2+C$。", "仅当 $\\alpha>-1$ 时收敛。此时下端原函数极限为 $0$，所以积分值为 $-1/(\\alpha+1)^2$。"],
        "practice": [("求 $\\int_0^1x^2\\log xdx$。", "$-1/9$。"), ("判断 $\\int_0^1x^{-1/2}|\\log x|dx$ 是否收敛。", "收敛，且值为 $4$。"), ("求 $x^a(\\log x)^2$ 在 $0$ 附近可积的条件。", "$a>-1$。")],
    },
    2015: {
        "category": "微分方程", "source": "閮4", "type": "Logistic 方程与可持续收获",
        "text": "考虑 $N'(t)=(1-N(t))N(t)-hN(t)$，$N(0)=N_0>0$，$h>0$。(1) 求 $N(t)$；(2) 求资源不枯竭的 $h$ 条件；(3) 求使稳态单位时间消耗量最大的 $h$。",
        "answer": ["方程为 $N'=N(K-N)$，$K=1-h$。$h\\ne1$ 时 $N(t)=K/[1+(K/N_0-1)e^{-Kt}]$；$h=1$ 时 $N(t)=N_0/(1+N_0t)$。", "若 $0<h<1$，则 $K>0$ 且 $N(t)\\to K=1-h>0$；$h\\ge1$ 时 $N(t)\\to0$。故不枯竭条件为 $0<h<1$。", "正稳态为 $N_*=1-h$，消耗量 $H(h)=hN_*=h(1-h)$，在 $h=1/2$ 取最大值 $1/4$。"],
        "practice": [("解 $y'=y(2-y),y(0)=1$。", "$y(t)=2/(1+e^{-2t})$。"), ("对 $N'=rN(1-N/K)-hN$ 求正稳态。", "$N_*=K(1-h/r)$，需 $0<h<r$。"), ("最大化 $h(1-h)$，$0<h<1$。", "导数 $1-2h=0$，故 $h=1/2$。")],
    },
    2016: {
        "category": "线性代数", "source": "閮3", "type": "对称矩阵谱分析",
        "text": "设 $a>0$，$A=\\begin{pmatrix}a+2&0&0\\\\0&1-a&1+a\\\\0&1+a&1-a\\end{pmatrix}$。(1) 求特征值和特征向量；(2) 证明存在非零 $x$ 使 $(x,Ax)=0$；(3) 证明每个二维子空间 $W$ 中都有单位向量 $x$ 使 $(x,Ax)\\ge2$。",
        "answer": ["特征值为 $a+2,2,-2a$，对应特征向量可取 $e_1,(0,1,1)^T,(0,1,-1)^T$。", "取分别位于特征值 $2$ 和 $-2a$ 的单位特征向量 $u,v$，令 $x=\\sqrt a\,u+v$，则 $(x,Ax)=2a-2a=0$。", "由维数公式，二维 $W$ 与由特征值 $a+2,2$ 的特征向量张成的二维空间交集非零。取交集中单位向量，其 Rayleigh 商不小于 $2$。"],
        "practice": [("求 $\\begin{pmatrix}p&q\\\\q&p\\end{pmatrix}$ 的特征值。", "$p+q,p-q$，特征向量为 $(1,1),(1,-1)$。"), ("已知对称矩阵有一正一负特征值，证明其二次型有非零零点。", "在两个单位特征向量的线性组合上平衡正负两项即可。"), ("说明两个 $\\mathbb R^3$ 的二维子空间必有非零交集。", "由 $\\dim(U\\cap V)\\ge2+2-3=1$。")],
    },
    2017: {
        "category": "微积分", "source": "閮1", "type": "调和数列与对数",
        "text": "(1) 证明 $0<x<1$ 时 $\\log(1-x)<-x$。(2) 令 $a_n=1+1/2+\\cdots+1/n-\\log n$，证明 $a_n$ 严格递减。(3) 证明 $\\{a_n\\}$ 收敛。",
        "answer": ["令 $g(x)=\\log(1-x)+x$，则 $g(0)=0$且 $g'(x)=-x/(1-x)<0$，得 (1)。", "$a_{n+1}-a_n=1/(n+1)-\\log(1+1/n)$。在 (1) 中取 $x=1/(n+1)$，得 $\\log(1+1/n)>1/(n+1)$，故差为负。", "由积分比较 $\\sum_{k=1}^n1/k>\\int_1^{n+1}dx/x=\\log(n+1)>\\log n$，故 $a_n>0$。它递减且有下界，因此收敛。"],
        "practice": [("证明 $\\log(1+x)<x$（$x>0$）。", "令 $h=x-\\log(1+x)$，$h'=x/(1+x)>0$。"), ("证明 $H_n-\\log(n+1)>0$。", "逐段使用 $1/k>\\int_k^{k+1}dx/x$后求和。"), ("求 $a_{n+1}-a_n$ 的渐近阶。", "由 $\\log(1+1/n)=1/n-1/(2n^2)+O(n^{-3})$，差为 $-1/(2n^2)+O(n^{-3})$。")],
    },
    2018: {
        "category": "微积分", "source": "閮1", "type": "混合偏导数不交换",
        "text": "定义 $f(x,y)=xy(x^2-y^2)/(x^2+y^2)$（$(x,y)\\ne(0,0)$），$f(0,0)=0$。(1) 求非原点处的 $f_x,f_y$；(2) 求 $f_x(0,0),f_y(0,0)$；(3) 求 $f_{xy}(0,0),f_{yx}(0,0)$；(4) 判断 $f_{xy}$ 在原点是否连续。",
        "answer": ["商法则给出 $f_x=y[(3x^2-y^2)(x^2+y^2)-2x^2(x^2-y^2)]/(x^2+y^2)^2$，$f_y=x[(x^2-3y^2)(x^2+y^2)-2y^2(x^2-y^2)]/(x^2+y^2)^2$。", "按定义 $f_x(0,0)=f_y(0,0)=0$。对 $y\\ne0$，$f_x(0,y)=-y$，故 $f_{xy}(0,0)=-1$；对 $x\\ne0$，$f_y(x,0)=x$，故 $f_{yx}(0,0)=1$。", "若 $f_{xy}$ 在原点连续，在邻域内偏导足够规则时混合偏导应交换，但上述两值不等。也可直接沿不同路径检查，故不连续。"],
        "practice": [("对 $f(x,y)=xy(x^2-y^2)/(x^2+y^2)$ 求 $f_x(0,y)$。", "$y\\ne0$ 时为 $-y$，$y=0$ 时为 $0$。"), ("说明为何 $f_{xy}(0,0)\\ne f_{yx}(0,0)$ 不违反 Clairaut 定理。", "定理要求混合偏导在原点附近连续，本题不满足该假设。"), ("若 $f\\in C^2$，比较 $f_{xy}$ 与 $f_{yx}$。", "由 Clairaut 定理，两者处处相等。")],
    },
}


def build(year, spec):
    qid = f"tohoku-{year}-math-q{''.join(ch for ch in spec['source'] if ch.isascii() and ch.isdigit()) or '01'}"
    answer = [{"label": f"步骤 {i}", "steps": [s]} for i, s in enumerate(spec["answer"], 1)]
    practices = []
    for i, (text, result) in enumerate(spec["practice"], 1):
        practices.append({
            "id": f"{qid}-practice-{i:02d}", "school": SCHOOL, "year": str(year), "text": text,
            "knowledge_points": [spec["type"], "基础计算与证明"], "question_type": "递进练习", "method": ["使用原题核心方法"],
            "solution_steps": ["识别与原题相同的结构", "执行计算或证明"],
            "math_structure": {"type": "exclusive_practice", "template": text, "variable_count": 2},
            "difficulty": min(4, 1 + i), "estimated_minutes": 4 + 2 * i,
            "answer": [{"label": "解答", "steps": [result]}],
        })
    return [{
        "id": qid, "school": SCHOOL, "year": str(year), "subject": f"{GRAD}_{MAJOR}", "text": spec["text"],
        "knowledge_points": [spec["type"], "大学数学综合应用"], "question_type": spec["type"], "method": ["详细推导"],
        "solution_steps": spec["answer"], "math_structure": {"type": "reviewed_exam_question", "template": spec["text"], "variable_count": 3},
        "difficulty": 3, "answer": answer, "practice_questions": practices,
        "source_question": spec["source"],
        "source_pdf": f"东北大学/情报科学研究科/数学教室/东北大学_情报科学研究科_数学教室_{year}_数学过去问.pdf",
        "source_type": "官方过去问", "subject_category": spec["category"],
    }]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    for year, spec in DATA.items():
        dest = args.output_root / "data" / spec["category"] / SCHOOL / GRAD / MAJOR / f"{year}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(build(year, spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(dest)


if __name__ == "__main__":
    main()
