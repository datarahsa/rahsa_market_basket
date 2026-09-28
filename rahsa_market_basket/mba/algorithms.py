"""
Empat pendekatan Market Basket Analysis yang ditulis mandiri (tanpa library pihak ketiga)
agar setiap algoritma benar benar berjalan dengan logikanya sendiri:

1. Apriori   : level wise, join + prune kandidat, lalu hitung ke semua transaksi.
2. FP Growth : membangun FP Tree lalu menambang pola lewat conditional tree.
3. AIS       : kandidat dibentuk langsung dari transaksi (on the fly), tanpa tahap prune.
               Sesuai paper aslinya, aturan hanya punya SATU produk di sisi konsekuen.
4. ARN       : Association Rule Network. Itemset ditambang secara vertikal (tidset bitmask),
               aturan disaring dengan uji signifikansi hipergeometrik, lalu dirangkai menjadi
               jaringan produk untuk melihat produk "hub" dan klaster produk.

Semua fungsi menerima list transaksi berupa frozenset nama produk.
Setiap algoritma mengembalikan dict {frozenset itemset: jumlah transaksi}.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations

import networkx as nx
import pandas as pd
from scipy.stats import hypergeom

RULE_COLUMNS = [
    "antecedent", "consequent", "jumlah_keranjang", "support",
    "confidence", "lift", "leverage", "conviction",
]


# ===========================================================================
# 1. APRIORI
# ===========================================================================
def apriori(transactions: list[frozenset], min_count: int, max_len: int) -> dict:
    item_counts = Counter(i for t in transactions for i in t)
    freq = {frozenset([i]): c for i, c in item_counts.items() if c >= min_count}
    frequent_items = {next(iter(s)) for s in freq}
    level = sorted(tuple([next(iter(s))]) for s in freq)
    k = 2
    while level and k <= max_len:
        prev = set(level)
        candidates = set()
        for i in range(len(level)):
            for j in range(i + 1, len(level)):
                a, b = level[i], level[j]
                if a[:-1] != b[:-1]:
                    break
                cand = a + (b[-1],)
                # prune: semua subset (k minus 1) harus frequent
                if all(sub in prev for sub in combinations(cand, k - 1)):
                    candidates.add(cand)
        if not candidates:
            break
        counts = Counter()
        for t in transactions:
            items = sorted(i for i in t if i in frequent_items)
            if len(items) < k:
                continue
            for combo in combinations(items, k):
                if combo in candidates:
                    counts[combo] += 1
        level = sorted(c for c, v in counts.items() if v >= min_count)
        for c in level:
            freq[frozenset(c)] = counts[c]
        k += 1
    return freq


# ===========================================================================
# 2. FP GROWTH
# ===========================================================================
class _Node:
    __slots__ = ("item", "count", "parent", "children")

    def __init__(self, item, parent):
        self.item = item
        self.count = 0
        self.parent = parent
        self.children = {}


def _build_fp_tree(weighted_paths, min_count):
    counts = Counter()
    for items, w in weighted_paths:
        for i in items:
            counts[i] += w
    counts = {i: c for i, c in counts.items() if c >= min_count}
    root = _Node(None, None)
    header = defaultdict(list)
    for items, w in weighted_paths:
        ordered = sorted((i for i in items if i in counts), key=lambda x: (-counts[x], x))
        node = root
        for i in ordered:
            child = node.children.get(i)
            if child is None:
                child = _Node(i, node)
                node.children[i] = child
                header[i].append(child)
            child.count += w
            node = child
    return header, counts


def fpgrowth(transactions: list[frozenset], min_count: int, max_len: int) -> dict:
    freq = {}
    header, counts = _build_fp_tree([(t, 1) for t in transactions], min_count)

    def mine(header, counts, suffix):
        # dari item paling jarang ke paling sering (bottom up)
        for item in sorted(counts, key=lambda x: (counts[x], x)):
            new_set = suffix | {item}
            freq[frozenset(new_set)] = counts[item]
            if len(new_set) >= max_len:
                continue
            paths = []
            for node in header[item]:
                path = []
                p = node.parent
                while p is not None and p.item is not None:
                    path.append(p.item)
                    p = p.parent
                if path:
                    paths.append((path, node.count))
            if paths:
                c_header, c_counts = _build_fp_tree(paths, min_count)
                if c_counts:
                    mine(c_header, c_counts, new_set)

    mine(header, counts, frozenset())
    return freq


# ===========================================================================
# 3. AIS
# ===========================================================================
def ais(transactions: list[frozenset], min_count: int, max_len: int) -> dict:
    item_counts = Counter(i for t in transactions for i in t)
    freq = {frozenset([i]): c for i, c in item_counts.items() if c >= min_count}
    frontier = {tuple([next(iter(s))]) for s in freq}
    k = 1
    while frontier and k < max_len:
        candidates = Counter()
        for t in transactions:
            if len(t) <= k:
                continue
            items = sorted(t)
            # kandidat dibentuk langsung dari isi transaksi: perluas itemset frequent
            # yang ada di keranjang dengan produk lain di keranjang yang sama
            for combo in combinations(items, k):
                if combo in frontier:
                    last = combo[-1]
                    for extra in items:
                        if extra > last:
                            candidates[combo + (extra,)] += 1
        frontier = {c for c, v in candidates.items() if v >= min_count}
        for c in frontier:
            freq[frozenset(c)] = candidates[c]
        k += 1
    return freq


# ===========================================================================
# 4. ARN (vertical mining + network)
# ===========================================================================
def arn_itemsets(transactions: list[frozenset], min_count: int, max_len: int) -> dict:
    tidsets = defaultdict(int)
    for idx, t in enumerate(transactions):
        bit = 1 << idx
        for i in t:
            tidsets[i] |= bit
    base = sorted((i, b) for i, b in tidsets.items() if b.bit_count() >= min_count)
    freq = {}

    def dfs(prefix, prefix_bits, candidates):
        for pos, (item, bits) in enumerate(candidates):
            new_bits = bits if prefix_bits is None else (prefix_bits & bits)
            cnt = new_bits.bit_count()
            if cnt < min_count:
                continue
            new_prefix = prefix + (item,)
            freq[frozenset(new_prefix)] = cnt
            if len(new_prefix) < max_len:
                dfs(new_prefix, new_bits, candidates[pos + 1:])

    dfs(tuple(), None, base)
    return freq


# ===========================================================================
# Pembentukan aturan asosiasi
# ===========================================================================
def rules_from_itemsets(freq: dict, n: int, single_consequent: bool = False) -> pd.DataFrame:
    rows = []
    for itemset, c_all in freq.items():
        if len(itemset) < 2:
            continue
        items = sorted(itemset)
        for r in range(1, len(items)):
            for ante in combinations(items, r):
                a = frozenset(ante)
                c = itemset - a
                if single_consequent and len(c) != 1:
                    continue
                c_a, c_c = freq[a], freq[c]
                conf = c_all / c_a
                p_c = c_c / n
                lift = conf / p_c
                leverage = c_all / n - (c_a / n) * p_c
                conviction = math.inf if conf >= 1 else (1 - p_c) / (1 - conf)
                rows.append((a, c, c_all, c_all / n, conf, lift, leverage, conviction))
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


def hypergeom_pvalue(n: int, c_ante: int, c_cons: int, c_both: int) -> float:
    """Peluang kebetulan melihat c_both atau lebih bila kedua sisi independen."""
    return float(hypergeom.sf(c_both - 1, n, c_cons, c_ante))


def run_all(transactions: list[frozenset], min_count: int, max_len: int,
            min_conf: float, min_lift: float, alpha: float) -> dict:
    """Menjalankan keempat algoritma dan mengembalikan hasil per algoritma."""
    n = len(transactions)
    out = {}

    f_ap = apriori(transactions, min_count, max_len)
    out["Apriori"] = {"itemsets": f_ap, "rules": rules_from_itemsets(f_ap, n)}

    f_fp = fpgrowth(transactions, min_count, max_len)
    out["FP Growth"] = {"itemsets": f_fp, "rules": rules_from_itemsets(f_fp, n)}

    f_ais = ais(transactions, min_count, max_len)
    out["AIS"] = {"itemsets": f_ais, "rules": rules_from_itemsets(f_ais, n, single_consequent=True)}

    f_arn = arn_itemsets(transactions, min_count, max_len)
    r_arn = rules_from_itemsets(f_arn, n, single_consequent=True)
    if not r_arn.empty:
        r_arn["p_value"] = [
            hypergeom_pvalue(n, f_arn[a], f_arn[c], k)
            for a, c, k in zip(r_arn["antecedent"], r_arn["consequent"], r_arn["jumlah_keranjang"])
        ]
        r_arn = r_arn[(r_arn["lift"] > 1) & (r_arn["p_value"] < alpha)]
    else:
        r_arn["p_value"] = []
    out["ARN"] = {"itemsets": f_arn, "rules": r_arn}

    for name in out:
        r = out[name]["rules"]
        out[name]["rules"] = r[(r["confidence"] >= min_conf) & (r["lift"] >= min_lift)] \
            .sort_values(["lift", "confidence"], ascending=False).reset_index(drop=True)
    return out


def build_arn_graph(arn_rules: pd.DataFrame, item_support: dict) -> nx.DiGraph:
    """Setiap aturan X ke y menjadi panah dari tiap produk di X menuju y, bobot = lift."""
    g = nx.DiGraph()
    for item, sup in item_support.items():
        g.add_node(item, support=sup)
    for a, c, lift, conf in zip(arn_rules["antecedent"], arn_rules["consequent"],
                                arn_rules["lift"], arn_rules["confidence"]):
        y = next(iter(c))
        for x in a:
            if g.has_edge(x, y):
                if lift > g[x][y]["lift"]:
                    g[x][y].update(lift=lift, confidence=conf)
            else:
                g.add_edge(x, y, lift=lift, confidence=conf)
    g.remove_nodes_from([n for n in list(g.nodes) if g.degree(n) == 0])
    return g


def arn_network_summary(g: nx.DiGraph):
    """PageRank (produk hub) dan klaster produk dari jaringan ARN."""
    if g.number_of_edges() == 0:
        return pd.DataFrame(columns=["produk", "pagerank", "masuk", "keluar", "klaster"]), []
    pr = nx.pagerank(g, weight="lift")
    und = g.to_undirected()
    try:
        comms = list(nx.community.greedy_modularity_communities(und, weight="lift"))
    except Exception:
        comms = [set(c) for c in nx.connected_components(und)]
    comm_of = {n: i + 1 for i, c in enumerate(comms) for n in c}
    df = pd.DataFrame({
        "produk": list(g.nodes),
        "pagerank": [pr[n] for n in g.nodes],
        "masuk": [g.in_degree(n) for n in g.nodes],
        "keluar": [g.out_degree(n) for n in g.nodes],
        "klaster": [comm_of.get(n, 0) for n in g.nodes],
    }).sort_values("pagerank", ascending=False).reset_index(drop=True)
    return df, [sorted(c) for c in comms if len(c) >= 2]
