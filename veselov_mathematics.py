#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════════
VESELOV MATHEMATICS FOR THERMODYNAMIC FILTERING
═══════════════════════════════════════════════════════════════════════════════════

Este módulo contiene las matemáticas puras de los papers de Vladimir Veselov
y su aplicación al Filtro de Probabilidad Termodinámica (TPF).

PAPERS DE REFERENCIA:
1. "Инновационный сумматор для гигантских чисел" (Innovative Adder for Giant Numbers)
2. "Интегрированная архитектура сумматора" (Integrated Adder Architecture)  
3. "Инновационный алгоритм умножения гигантских чисел" (Innovative Multiplication Algorithm)

TRES INNOVACIONES CLAVE:
1. Representación Jerárquica con Crecimiento Exponencial
2. Binomial Heaps para Gestión de Componentes
3. Representación como Arrays de Potencias de Dos

APLICACIÓN AL TPF:
- Las latencias de shares se tratan como "números gigantes" en escala temporal
- La estructura jerárquica captura patrones en múltiples escalas de tiempo
- Los Binomial Heaps permiten merge eficiente O(log n) de distribuciones
- DVFS adapta la intensidad del filtro dinámicamente

Author: Francisco Angulo de Lafuente
Based on: Veselov Research Group Papers (January 2026)
"""

import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Deque
from abc import ABC, abstractmethod


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 1: FUNDAMENTOS MATEMÁTICOS
# ═══════════════════════════════════════════════════════════════════════════════════

"""
TEORÍA: Representación Jerárquica con Crecimiento Exponencial

Del paper: Un número N se divide en L niveles, donde cada nivel k procesa
un rango de bits de tamaño exponencialmente creciente.

FÓRMULAS CLAVE:

    Sₖ = 64 · 2ᵏ    (tamaño del nivel k en bits)
    
    L = ⌈log₂(n/64 + 1)⌉    (número total de niveles)

Para un número de n bits:
    - Nivel 0: procesa bits [0, 64)
    - Nivel 1: procesa bits [64, 192)      → 64·2¹ = 128 bits
    - Nivel 2: procesa bits [192, 448)     → 64·2² = 256 bits
    - Nivel k: procesa bits [Σᵢ₌₀ᵏ⁻¹ Sᵢ, Σᵢ₌₀ᵏ Sᵢ)

APLICACIÓN AL TPF:
    - Nivel 0: Variaciones de microsegundos (alta frecuencia)
    - Nivel 1: Variaciones de milisegundos
    - Nivel 2: Variaciones de segundos
    - Nivel k: Patrones de escala temporal 2ᵏ mayor
"""

# Constantes fundamentales
WORD_SIZE = 64  # Tamaño base en bits (del paper)


def compute_level_size(k: int, word_size: int = WORD_SIZE) -> int:
    """
    Calcula el tamaño del nivel k en bits.
    
    Fórmula: Sₖ = 64 · 2ᵏ para k > 0, S₀ = 64
    
    Args:
        k: Índice del nivel (0, 1, 2, ...)
        word_size: Tamaño base (por defecto 64 bits)
    
    Returns:
        Tamaño del nivel en bits
    """
    if k == 0:
        return word_size
    return word_size * (2 ** k)


def compute_num_levels(n_bits: int, word_size: int = WORD_SIZE) -> int:
    """
    Calcula el número de niveles necesarios para n bits.
    
    Fórmula: L = ⌈log₂(n/64 + 1)⌉
    
    Args:
        n_bits: Número total de bits a procesar
        word_size: Tamaño base
    
    Returns:
        Número de niveles L
    """
    if n_bits <= 0:
        return 1
    return math.ceil(math.log2(n_bits / word_size + 1))


def compute_level_boundaries(num_levels: int) -> List[Tuple[int, int]]:
    """
    Calcula los límites [start, end) de cada nivel.
    
    Returns:
        Lista de tuplas (bit_start, bit_end) para cada nivel
    """
    boundaries = []
    current_start = 0
    
    for k in range(num_levels):
        size = compute_level_size(k)
        boundaries.append((current_start, current_start + size))
        current_start += size
    
    return boundaries


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 2: REPRESENTACIÓN COMO POTENCIAS DE DOS
# ═══════════════════════════════════════════════════════════════════════════════════

"""
TEORÍA: Representación como Arrays de Potencias de Dos

Del paper: Un número N se expresa como suma de potencias de dos:

    N = Σ 2^p(u)    para todos los nodos u en la estructura

Cada nodo almacena un EXPONENTE p, representando la contribución 2^p.

VENTAJAS:
1. Operaciones de shift son triviales: incrementar/decrementar exponentes
2. Compresión natural de números dispersos (sparse)
3. Paralelización por independencia de exponentes

OPERACIONES FUNDAMENTALES:

    SHIFT_LEFT(H) = {p + 1 | p ∈ H}     (multiplicar por 2)
    SHIFT_RIGHT(H) = {p - 1 | p ∈ H, p > 0}   (dividir por 2)

APLICACIÓN AL TPF:
    - Cada latencia t se representa como 2^p donde p = ⌊log₂(t)⌋
    - El exponente p indica la "escala temporal" de la latencia
    - Latencias similares tienen exponentes cercanos → coherencia
"""


def value_to_exponent(value: float) -> int:
    """
    Convierte un valor a su exponente de potencia de dos.
    
    Fórmula: p = ⌊log₂(value)⌋
    
    El valor se representa como 2^p (aproximación)
    
    Args:
        value: Valor positivo a convertir
    
    Returns:
        Exponente p tal que 2^p ≈ value
    """
    if value <= 0:
        return 0
    return int(math.log2(max(1, value)))


def exponent_to_value(exponent: int) -> float:
    """
    Convierte un exponente de vuelta a valor.
    
    Fórmula: value = 2^p
    """
    return 2.0 ** exponent


def value_to_level(value: float, num_levels: int, scale_factor: float = 0.001) -> int:
    """
    Determina a qué nivel jerárquico pertenece un valor.
    
    Basado en la magnitud logarítmica del valor.
    
    Args:
        value: Valor a clasificar (ej: latencia en ms)
        num_levels: Número total de niveles
        scale_factor: Factor de escala para mapear a niveles
    
    Returns:
        Índice del nivel k ∈ [0, num_levels-1]
    """
    if value <= 0:
        return 0
    
    log_val = math.log2(max(1, value))
    
    for k in range(num_levels - 1, -1, -1):
        level_threshold = compute_level_size(k) * scale_factor
        if log_val >= level_threshold:
            return k
    
    return 0


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 3: BINOMIAL HEAPS
# ═══════════════════════════════════════════════════════════════════════════════════

"""
TEORÍA: Binomial Heaps para Gestión de Componentes

Del paper: Una Binomial Heap de orden k tiene las siguientes propiedades:

    1. Contiene 2^k nodos
    2. Altura del árbol = k
    3. Raíz tiene grado k
    4. Para i = 0,1,...,k-1: raíz tiene hijo que es raíz de árbol binomial de orden i

COMPLEJIDAD:
    - Merge: O(log n)
    - Insert: O(log n)
    - Extract-Min: O(log n)
    - Find-Min: O(1) con puntero

OPERACIÓN CLAVE - MERGE (Algorithm 3 del paper):
    Fusionar dos heaps es análogo a sumar números binarios:
    - Dos árboles de orden k se combinan en uno de orden k+1
    - Similar a: 2^k + 2^k = 2^(k+1)

NORMALIZACIÓN (Algorithm 4 del paper):
    Elimina conflictos cuando hay exponentes duplicados:
    - Dos nodos con exponente p → un nodo con exponente p+1
    - Representa la propagación de carry en aritmética binaria
"""


@dataclass
class BinomialNode:
    """
    Nodo de un Binomial Heap.
    
    Atributos del paper:
    - degree: Orden k del nodo (número de hijos)
    - value: Valor almacenado (latencia en TPF)
    - exponent: Exponente p tal que contribuye 2^p
    """
    degree: int = 0
    value: float = 0.0
    exponent: int = 0
    parent: Optional['BinomialNode'] = None
    children: List['BinomialNode'] = field(default_factory=list)
    sibling: Optional['BinomialNode'] = None
    
    def __lt__(self, other: 'BinomialNode') -> bool:
        return self.value < other.value


class BinomialHeap:
    """
    Implementación de Binomial Heap según los papers de Veselov.
    
    Usado en TPF para:
    - Gestionar distribuciones de timing por nivel jerárquico
    - Merge eficiente O(log n) de muestras de múltiples fuentes
    - Operaciones SHIFT_LEFT/SHIFT_RIGHT para escalar
    """
    
    def __init__(self, level: int = 0):
        """
        Args:
            level: Nivel jerárquico k al que pertenece este heap
        """
        self.roots: List[BinomialNode] = []
        self.level = level
        self.size = 0
        self._min_node: Optional[BinomialNode] = None
        
        # Rango de bits que procesa este nivel: [64·2^(k-1), 64·2^k)
        self.bit_range = (
            WORD_SIZE * (2 ** (level - 1)) if level > 0 else 0,
            WORD_SIZE * (2 ** level)
        )
    
    def _link(self, y: BinomialNode, z: BinomialNode) -> BinomialNode:
        """
        Enlaza dos árboles binomiales del mismo orden.
        Hace y hijo de z.
        
        Resultado: árbol de orden k+1
        """
        y.parent = z
        y.sibling = z.children[0] if z.children else None
        z.children.insert(0, y)
        z.degree += 1
        return z
    
    def _merge_root_lists(self, h1_roots: List[BinomialNode], 
                          h2_roots: List[BinomialNode]) -> List[BinomialNode]:
        """Fusiona listas de raíces ordenadas por grado."""
        merged = []
        i, j = 0, 0
        
        while i < len(h1_roots) and j < len(h2_roots):
            if h1_roots[i].degree <= h2_roots[j].degree:
                merged.append(h1_roots[i])
                i += 1
            else:
                merged.append(h2_roots[j])
                j += 1
        
        merged.extend(h1_roots[i:])
        merged.extend(h2_roots[j:])
        return merged
    
    def merge(self, other: 'BinomialHeap') -> 'BinomialHeap':
        """
        Algorithm 3: ParallelHeapMerge (simplificado para un nivel)
        
        Fusiona dos binomial heaps en O(log n).
        Análogo a sumar dos números en representación binaria.
        
        Args:
            other: Heap a fusionar con este
        
        Returns:
            self (modificado)
        """
        if not other.roots:
            return self
        if not self.roots:
            self.roots = other.roots
            self.size = other.size
            self._update_min()
            return self
        
        # Fusionar listas de raíces
        merged = self._merge_root_lists(self.roots, other.roots)
        self.size += other.size
        
        if not merged:
            self.roots = []
            self._update_min()
            return self
        
        # Unir árboles del mismo grado (como carry en suma binaria)
        new_roots = []
        idx = 0
        
        while idx < len(merged):
            curr = merged[idx]
            
            # Verificar si hay siguiente del mismo grado
            if idx + 1 < len(merged) and merged[idx + 1].degree == curr.degree:
                next_node = merged[idx + 1]
                # Verificar si hay un tercero del mismo grado
                if idx + 2 < len(merged) and merged[idx + 2].degree == curr.degree:
                    # Tres del mismo grado: mantener uno, fusionar dos
                    new_roots.append(curr)
                    # Fusionar los siguientes dos
                    if next_node.value <= merged[idx + 2].value:
                        linked = self._link(merged[idx + 2], next_node)
                    else:
                        linked = self._link(next_node, merged[idx + 2])
                    merged[idx + 2] = linked
                    idx += 2
                else:
                    # Dos del mismo grado: fusionar
                    if curr.value <= next_node.value:
                        linked = self._link(next_node, curr)
                    else:
                        linked = self._link(curr, next_node)
                    merged[idx + 1] = linked
                    idx += 1
            else:
                new_roots.append(curr)
                idx += 1
        
        self.roots = new_roots
        self._update_min()
        return self
    
    def insert(self, value: float, exponent: int = None):
        """
        Inserta un valor con su exponente de potencia de dos.
        
        Args:
            value: Valor a insertar (ej: latencia)
            exponent: Exponente p (si None, se calcula automáticamente)
        """
        if exponent is None:
            exponent = value_to_exponent(value)
        
        node = BinomialNode(degree=0, value=value, exponent=exponent)
        temp_heap = BinomialHeap(self.level)
        temp_heap.roots = [node]
        temp_heap.size = 1
        self.merge(temp_heap)
    
    def get_min(self) -> Optional[float]:
        """Obtiene el valor mínimo en O(1)."""
        return self._min_node.value if self._min_node else None
    
    def extract_min(self) -> Optional[BinomialNode]:
        """Extrae el nodo con valor mínimo en O(log n)."""
        if not self._min_node:
            return None
        
        min_node = self._min_node
        self.roots.remove(min_node)
        
        # Los hijos del mínimo forman un nuevo heap
        if min_node.children:
            child_heap = BinomialHeap(self.level)
            child_heap.roots = list(reversed(min_node.children))
            for child in child_heap.roots:
                child.parent = None
            child_heap.size = sum(2 ** c.degree for c in child_heap.roots)
            self.merge(child_heap)
        
        self.size -= 1
        self._update_min()
        return min_node
    
    def _update_min(self):
        """Actualiza el puntero al mínimo."""
        self._min_node = None
        for root in self.roots:
            if self._min_node is None or root.value < self._min_node.value:
                self._min_node = root
    
    # ═══════════════════════════════════════════════════════════════
    # OPERACIONES DE SHIFT (del paper)
    # ═══════════════════════════════════════════════════════════════
    
    def shift_left(self):
        """
        SHIFT_LEFT(H) = {p + 1 | p ∈ H}
        
        Multiplica todos los valores representados por 2.
        En términos de exponentes: incrementa todos los exponentes.
        
        Aplicación TPF: Escalar patrones a nivel temporal superior.
        """
        def _shift_node(node: BinomialNode):
            node.exponent += 1
            for child in node.children:
                _shift_node(child)
        
        for root in self.roots:
            _shift_node(root)
    
    def shift_right(self):
        """
        SHIFT_RIGHT(H) = {p - 1 | p ∈ H, p > 0}
        
        Divide todos los valores representados por 2.
        Elimina nodos con exponente que se volvería negativo.
        
        Aplicación TPF: Escalar patrones a nivel temporal inferior.
        """
        def _shift_node(node: BinomialNode) -> bool:
            if node.exponent <= 0:
                return False  # Eliminar este nodo
            node.exponent -= 1
            node.children = [c for c in node.children if _shift_node(c)]
            return True
        
        self.roots = [r for r in self.roots if _shift_node(r)]
        self._update_min()
        # Recalcular tamaño
        self.size = self._count_nodes()
    
    def _count_nodes(self) -> int:
        """Cuenta todos los nodos en el heap."""
        def _count(node: BinomialNode) -> int:
            return 1 + sum(_count(c) for c in node.children)
        return sum(_count(r) for r in self.roots)
    
    # ═══════════════════════════════════════════════════════════════
    # NORMALIZACIÓN (Algorithm 4 del paper)
    # ═══════════════════════════════════════════════════════════════
    
    def normalize(self) -> 'BinomialHeap':
        """
        Algorithm 4: NormalizeHeap
        
        Elimina conflictos cuando hay exponentes duplicados:
        - Dos nodos con exponente p → un nodo con exponente p+1
        - Análogo a propagación de carry: 2^p + 2^p = 2^(p+1)
        
        Aplicación TPF: Consolida muestras redundantes en el mismo
        rango temporal, creando una representación canónica.
        
        Returns:
            self (normalizado)
        """
        # Paso 1: Recolectar todos los exponentes y valores
        exponent_map: Dict[int, List[float]] = defaultdict(list)
        
        def _collect_all(node: BinomialNode):
            exponent_map[node.exponent].append(node.value)
            for child in node.children:
                _collect_all(child)
        
        for root in self.roots:
            _collect_all(root)
        
        # Paso 2: Normalizar - combinar duplicados
        # Similar a carry propagation en suma binaria
        sorted_exponents = sorted(exponent_map.keys())
        normalized: Dict[int, float] = {}
        
        for exp in sorted_exponents:
            values = exponent_map[exp]
            
            # Mientras haya pares, combinarlos
            while len(values) >= 2:
                v1, v2 = values.pop(), values.pop()
                # Combinar: promedio del valor, incrementar exponente
                combined_value = (v1 + v2) / 2
                # Propagar al siguiente exponente
                if (exp + 1) not in exponent_map:
                    exponent_map[exp + 1] = []
                exponent_map[exp + 1].append(combined_value)
            
            # Si queda uno, mantenerlo
            if values:
                normalized[exp] = values[0]
        
        # Paso 3: Reconstruir heap con valores normalizados
        self.roots = []
        self.size = 0
        self._min_node = None
        
        for exp in sorted(normalized.keys()):
            self.insert(normalized[exp], exp)
        
        return self
    
    # ═══════════════════════════════════════════════════════════════
    # ANÁLISIS Y MÉTRICAS
    # ═══════════════════════════════════════════════════════════════
    
    def get_exponent_distribution(self) -> Dict[int, int]:
        """
        Obtiene la distribución de exponentes en el heap.
        
        Returns:
            Dict[exponente -> cuenta]
        """
        distribution: Dict[int, int] = defaultdict(int)
        
        def _collect(node: BinomialNode):
            distribution[node.exponent] += 1
            for child in node.children:
                _collect(child)
        
        for root in self.roots:
            _collect(root)
        
        return dict(distribution)
    
    def compute_coherence(self) -> float:
        """
        Calcula la coherencia del heap basada en distribución de exponentes.
        
        Coherencia alta = exponentes concentrados = patrón temporal consistente
        Coherencia baja = exponentes dispersos = ruido/entropía
        
        Returns:
            Valor en [0, 1] donde 1 = máxima coherencia
        """
        dist = self.get_exponent_distribution()
        if not dist:
            return 0.0
        
        values = list(dist.values())
        if len(values) < 2:
            return 1.0
        
        # Coeficiente de variación (CV) de la distribución
        mean = statistics.mean(values)
        if mean == 0:
            return 0.0
        
        std = statistics.stdev(values)
        cv = std / mean
        
        # Transformar CV a coherencia: CV bajo = coherencia alta
        coherence = 1 / (1 + cv)
        return coherence
    
    def __repr__(self) -> str:
        return f"BinomialHeap(level={self.level}, size={self.size}, min={self.get_min()})"


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 4: ESTRUCTURA JERÁRQUICA COMPLETA
# ═══════════════════════════════════════════════════════════════════════════════════

"""
TEORÍA: Integración de las Tres Innovaciones

Del paper: Un número N se representa como:

    N = ⋃(k=0 to L-1) H_N^(k)

Donde H_N^(k) es la binomial heap del nivel k, conteniendo exponentes p tales que:

    H_N^(k) = {p | 2^p está presente en N y 64·2^(k-1) ≤ p < 64·2^k}

La operación de SUMA se implementa como:
    1. Merge paralelo de heaps por nivel
    2. Normalización dentro de cada nivel
    3. Propagación de carries entre niveles
"""


class HierarchicalStructure:
    """
    Estructura Jerárquica con Crecimiento Exponencial.
    
    Integra las tres innovaciones de Veselov:
    1. Niveles con tamaño Sₖ = 64·2ᵏ
    2. Binomial Heaps en cada nivel
    3. Representación como potencias de dos
    
    Aplicación TPF:
    - Nivel 0: Micro-variaciones (ruido de alta frecuencia)
    - Nivel 1: Variaciones de milisegundos
    - Nivel 2+: Patrones de escala creciente
    """
    
    def __init__(self, num_levels: int = 6):
        """
        Args:
            num_levels: Número de niveles L en la jerarquía
        """
        self.num_levels = num_levels
        self.levels: List[BinomialHeap] = [
            BinomialHeap(level=k) for k in range(num_levels)
        ]
        
        # Tamaños de nivel: Sₖ = 64·2ᵏ
        self.level_sizes = [compute_level_size(k) for k in range(num_levels)]
        
        # Estadísticas por nivel
        self.level_stats = [{
            'count': 0,
            'sum': 0.0,
            'sum_sq': 0.0,
            'mean': 0.0,
            'variance': 0.0,
            'std': 0.0
        } for _ in range(num_levels)]
        
        self.total_count = 0
    
    def insert(self, value: float):
        """
        Inserta un valor en el nivel jerárquico apropiado.
        
        Algorithm 1: InitializeHierarchy (adaptado para inserción)
        
        Args:
            value: Valor a insertar (ej: latencia en ms)
        """
        # Determinar nivel basado en magnitud
        level = value_to_level(value, self.num_levels)
        exponent = value_to_exponent(value)
        
        # Insertar en el heap del nivel correspondiente
        self.levels[level].insert(value, exponent)
        
        # Actualizar estadísticas (Welford's online algorithm)
        stats = self.level_stats[level]
        stats['count'] += 1
        n = stats['count']
        
        delta = value - stats['mean']
        stats['mean'] += delta / n
        delta2 = value - stats['mean']
        stats['sum_sq'] += delta * delta2
        
        if n > 1:
            stats['variance'] = stats['sum_sq'] / (n - 1)
            stats['std'] = math.sqrt(stats['variance'])
        
        self.total_count += 1
    
    def parallel_merge(self, other: 'HierarchicalStructure'):
        """
        Algorithm 3: ParallelHeapMerge
        
        Fusiona otra estructura jerárquica en esta.
        Cada nivel se procesa independientemente (paralelizable).
        
        Args:
            other: Estructura a fusionar
        """
        for k in range(min(self.num_levels, other.num_levels)):
            # Merge del nivel k
            self.levels[k].merge(other.levels[k])
            # Normalizar para manejar carries
            self.levels[k].normalize()
        
        # Procesar carries entre niveles
        self._process_inter_level_carries()
    
    def _process_inter_level_carries(self, max_size_per_level: int = 1024):
        """
        Procesa overflow entre niveles.
        
        Cuando un nivel excede su capacidad, promueve elementos al siguiente.
        """
        for k in range(self.num_levels - 1):
            while self.levels[k].size > max_size_per_level:
                # Extraer mínimo y promover
                node = self.levels[k].extract_min()
                if node:
                    # Shift del exponente para el siguiente nivel
                    self.levels[k + 1].insert(node.value, node.exponent + 1)
    
    def compute_resonance_score(self) -> float:
        """
        Calcula el score de resonancia global de la estructura.
        
        Basado en la fórmula de energía del paper:
            E = k · log(n) · V² · f · αeff
        
        Resonancia alta = baja "energía" = estructura coherente
        
        Returns:
            Score en [0, 1] donde 1 = máxima resonancia
        """
        if self.total_count < 10:
            return 0.5  # Insuficientes datos
        
        scores = []
        weights = []
        
        for k, heap in enumerate(self.levels):
            if heap.size > 0:
                # Coherencia del heap
                coherence = heap.compute_coherence()
                # Peso por nivel (niveles superiores = patrones macro = más importantes)
                weight = k + 1
                scores.append(coherence * weight)
                weights.append(weight)
        
        if not scores:
            return 0.5
        
        # Promedio ponderado
        return sum(scores) / sum(weights)
    
    def get_level_analysis(self) -> List[Dict]:
        """
        Análisis detallado por nivel.
        
        Returns:
            Lista de diccionarios con métricas por nivel
        """
        analysis = []
        for k in range(self.num_levels):
            heap = self.levels[k]
            stats = self.level_stats[k]
            
            analysis.append({
                'level': k,
                'size_bits': self.level_sizes[k],
                'heap_size': heap.size,
                'mean': stats['mean'],
                'std': stats['std'],
                'coherence': heap.compute_coherence(),
                'exponent_distribution': heap.get_exponent_distribution()
            })
        
        return analysis
    
    def __repr__(self) -> str:
        sizes = [h.size for h in self.levels]
        return f"HierarchicalStructure(levels={self.num_levels}, sizes={sizes}, total={self.total_count})"


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 5: DVFS - CONTROL ADAPTATIVO
# ═══════════════════════════════════════════════════════════════════════════════════

"""
TEORÍA: Dynamic Voltage and Frequency Scaling (DVFS)

Del paper: La potencia dinámica se modela como:

    P_dyn = α · C · V² · f

Donde:
    α = coeficiente de actividad (≈ 0.2 efectivo)
    C = capacitancia de switching
    V = voltaje
    f = frecuencia

ESTRATEGIA ADAPTATIVA (Algorithm 2):
    1. Si temperatura > T_max: reducir frecuencia 10%
    2. Si temperatura < T_max - Δ: aumentar frecuencia 10%
    3. Voltaje sigue a frecuencia: V ∝ √f (para eficiencia óptima)

APLICACIÓN AL TPF:
    - "Frecuencia" = Intensidad del filtro (qué tan agresivo)
    - "Voltaje" = Sensibilidad de umbrales
    - "Temperatura" = Tasa de rechazo (carga del sistema)
"""


@dataclass
class DVFSState:
    """Estado del controlador DVFS."""
    frequency: float = 0.5      # Intensidad del filtro [0, 1]
    voltage: float = 0.7        # Sensibilidad de umbrales [0, 1]
    temperature: float = 0.5    # Carga/tasa de rechazo [0, 1]
    
    # Constantes del paper
    alpha_eff: float = 0.2      # Coeficiente de actividad efectivo
    
    def compute_energy(self) -> float:
        """
        Calcula la "energía" del sistema.
        
        E = α · V² · f
        """
        return self.alpha_eff * (self.voltage ** 2) * self.frequency


class DVFSController:
    """
    Controlador DVFS para adaptación dinámica del filtro.
    
    Implementa Algorithm 2 del paper adaptado para TPF.
    """
    
    def __init__(self):
        self.state = DVFSState()
        
        # Parámetros de control
        self.f_min = 0.25       # Frecuencia mínima
        self.f_max = 1.0        # Frecuencia máxima
        self.t_max = 0.9        # Temperatura máxima
        self.t_delta = 0.1      # Banda de histéresis
        
        # Historial para suavizado
        self.history: Deque[float] = deque(maxlen=50)
    
    def update(self, load_factor: float, rejection_rate: float):
        """
        Algorithm 2: DVFSController (adaptado)
        
        Actualiza parámetros DVFS basándose en carga actual.
        
        Args:
            load_factor: Factor de carga [0, 1]
            rejection_rate: Tasa de rechazo [0, 1]
        """
        self.history.append(load_factor)
        self.state.temperature = rejection_rate
        
        # Calcular frecuencia objetivo basada en carga
        f_target = self.f_min + (self.f_max - self.f_min) * load_factor
        
        # Ajuste por temperatura (Algorithm 2, líneas 5-9)
        if self.state.temperature > self.t_max:
            # Demasiados rechazos → reducir intensidad del filtro
            f_target *= 0.9
        elif self.state.temperature < (self.t_max - self.t_delta):
            # Margen para ser más agresivo
            f_target *= 1.1
        
        # Limitar a rango válido
        self.state.frequency = max(self.f_min, min(self.f_max, f_target))
        
        # Voltaje sigue a frecuencia (relación cuadrática del paper)
        # V ∝ √f para eficiencia óptima
        v_target = math.sqrt(self.state.frequency / self.f_max)
        self.state.voltage = max(0.5, min(1.0, v_target))
    
    def get_adjusted_thresholds(self, 
                                base_z_threshold: float,
                                base_cv_threshold: float) -> Tuple[float, float]:
        """
        Obtiene umbrales ajustados por DVFS.
        
        Args:
            base_z_threshold: Umbral base de z-score
            base_cv_threshold: Umbral base de coeficiente de variación
        
        Returns:
            (z_threshold_ajustado, cv_threshold_ajustado)
        """
        # Escalar umbrales por "voltaje" y "frecuencia"
        z_adj = base_z_threshold * self.state.voltage
        cv_adj = base_cv_threshold * self.state.frequency
        return z_adj, cv_adj
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas del controlador."""
        return {
            'frequency': self.state.frequency,
            'voltage': self.state.voltage,
            'temperature': self.state.temperature,
            'energy': self.state.compute_energy(),
            'load_avg': statistics.mean(self.history) if self.history else 0
        }


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 6: FILTRO TERMODINÁMICO CON MATEMÁTICAS DE VESELOV
# ═══════════════════════════════════════════════════════════════════════════════════

"""
INTEGRACIÓN FINAL: TPF + VESELOV

El Filtro de Probabilidad Termodinámica usa las matemáticas de Veselov para:

1. ESTRUCTURA JERÁRQUICA:
   - Captura patrones en múltiples escalas temporales
   - Nivel k detecta variaciones de período ~2^k

2. BINOMIAL HEAPS:
   - Merge eficiente de distribuciones de timing
   - Normalización elimina redundancia

3. POTENCIAS DE DOS:
   - Clasificación natural de magnitudes
   - Operaciones shift para escalar entre niveles

4. DVFS:
   - Adapta agresividad del filtro
   - Balanceo energía/rendimiento

FLUJO DE EVALUACIÓN:

    Latencia → Nivel jerárquico → Heap insertion → 
    → Coherencia check → DVFS adjustment → Decisión
"""


@dataclass 
class FilterDecision:
    """Resultado de la evaluación del filtro."""
    passed: bool
    decision: str
    z_score: float
    hierarchy_level: int
    exponent: int
    resonance_score: float
    coherence: float
    dvfs_energy: float


class VeselovThermodynamicFilter:
    """
    Filtro Termodinámico con Matemáticas de Veselov.
    
    Combina las tres innovaciones para filtrado inteligente de shares.
    """
    
    def __init__(self, num_levels: int = 6):
        # Estructura jerárquica
        self.hierarchy = HierarchicalStructure(num_levels)
        
        # Controlador DVFS
        self.dvfs = DVFSController()
        
        # Estadísticas globales
        self.samples: Deque[float] = deque(maxlen=5000)
        self.mean = 0.0
        self.std = 1.0
        self.calibrated = False
        
        # Umbrales base
        self.z_threshold_base = 0.8
        self.cv_threshold_base = 0.95
        self.resonance_threshold = 0.5
        
        # Contadores
        self.total_evaluated = 0
        self.total_passed = 0
        self.total_filtered = 0
        
        # Calibración
        self.calibration_samples = 100
    
    def update(self, value: float):
        """
        Actualiza el filtro con un nuevo valor.
        
        Args:
            value: Latencia o timing a procesar
        """
        # Actualizar muestras globales
        self.samples.append(value)
        
        # Insertar en estructura jerárquica
        self.hierarchy.insert(value)
        
        # Actualizar estadísticas globales
        if len(self.samples) >= self.calibration_samples:
            self.mean = statistics.mean(self.samples)
            self.std = statistics.stdev(self.samples) if len(self.samples) > 1 else 1.0
            
            if not self.calibrated:
                self.calibrated = True
            
            # Actualizar DVFS
            load = len(self.samples) / 5000  # Normalizar
            rejection_rate = self.total_filtered / max(1, self.total_evaluated)
            self.dvfs.update(load, rejection_rate)
    
    def evaluate(self, value: float, force_pass: bool = False) -> FilterDecision:
        """
        Evalúa un valor a través del filtro multi-tier.
        
        TIER 1: Z-score (timing básico)
        TIER 2: Coherencia jerárquica
        TIER 3: Resonancia global
        
        Args:
            value: Valor a evaluar
            force_pass: Si True, fuerza paso (para heartbeat)
        
        Returns:
            FilterDecision con resultado y métricas
        """
        self.total_evaluated += 1
        
        # Métricas de Veselov
        level = value_to_level(value, self.hierarchy.num_levels)
        exponent = value_to_exponent(value)
        resonance = self.hierarchy.compute_resonance_score()
        coherence = self.hierarchy.levels[level].compute_coherence()
        dvfs_energy = self.dvfs.state.compute_energy()
        
        # Z-score
        z_score = (value - self.mean) / (self.std + 1e-9) if self.calibrated else 0.0
        
        # Umbrales ajustados por DVFS
        z_thresh, cv_thresh = self.dvfs.get_adjusted_thresholds(
            self.z_threshold_base, 
            self.cv_threshold_base
        )
        
        # === EVALUACIÓN ===
        
        # No calibrado: pasar
        if not self.calibrated:
            self.total_passed += 1
            return FilterDecision(
                passed=True,
                decision="CALIBRATING",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        # Forzar paso
        if force_pass:
            self.total_passed += 1
            return FilterDecision(
                passed=True,
                decision="FORCED",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        # TIER 1: Z-score check
        if z_score > z_thresh:
            self.total_filtered += 1
            return FilterDecision(
                passed=False,
                decision="FILTERED_SLOW",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        # TIER 2: Coherencia check
        if coherence < 0.3:  # Muy baja coherencia en el nivel
            self.total_filtered += 1
            return FilterDecision(
                passed=False,
                decision="FILTERED_INCOHERENT",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        # TIER 3: Resonancia global
        is_super_resonant = z_score < -0.5 and resonance > 0.7
        
        if is_super_resonant:
            self.total_passed += 1
            return FilterDecision(
                passed=True,
                decision="SUPER_RESONANT",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        if resonance >= self.resonance_threshold:
            self.total_passed += 1
            return FilterDecision(
                passed=True,
                decision="RESONANT",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        # Borde: baja resonancia pero pasó timing
        if dvfs_energy < self.dvfs.state.alpha_eff:
            self.total_passed += 1
            return FilterDecision(
                passed=True,
                decision="MARGINAL",
                z_score=z_score,
                hierarchy_level=level,
                exponent=exponent,
                resonance_score=resonance,
                coherence=coherence,
                dvfs_energy=dvfs_energy
            )
        
        self.total_filtered += 1
        return FilterDecision(
            passed=False,
            decision="FILTERED_LOW_RESONANCE",
            z_score=z_score,
            hierarchy_level=level,
            exponent=exponent,
            resonance_score=resonance,
            coherence=coherence,
            dvfs_energy=dvfs_energy
        )
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas completas del filtro."""
        return {
            'calibrated': self.calibrated,
            'total_evaluated': self.total_evaluated,
            'total_passed': self.total_passed,
            'total_filtered': self.total_filtered,
            'pass_rate': self.total_passed / max(1, self.total_evaluated),
            'filter_rate': self.total_filtered / max(1, self.total_evaluated),
            'mean': self.mean,
            'std': self.std,
            'resonance_score': self.hierarchy.compute_resonance_score(),
            'dvfs': self.dvfs.get_stats(),
            'hierarchy': self.hierarchy.get_level_analysis()
        }


# ═══════════════════════════════════════════════════════════════════════════════════
# PARTE 7: EJEMPLOS Y DEMOSTRACIÓN
# ═══════════════════════════════════════════════════════════════════════════════════

def demo_level_sizes():
    """Demuestra los tamaños de nivel jerárquico."""
    print("=" * 60)
    print("TAMAÑOS DE NIVEL JERÁRQUICO (Sₖ = 64·2ᵏ)")
    print("=" * 60)
    
    for k in range(8):
        size = compute_level_size(k)
        print(f"  Nivel {k}: Sₖ = {size:,} bits ({size/8:,.0f} bytes)")
    
    print()
    print("Número de niveles para diferentes tamaños:")
    for n_bits in [1000, 10_000, 100_000, 1_000_000, 10_000_000]:
        L = compute_num_levels(n_bits)
        print(f"  n = {n_bits:>10,} bits → L = {L} niveles")


def demo_powers_of_two():
    """Demuestra la representación como potencias de dos."""
    print("\n" + "=" * 60)
    print("REPRESENTACIÓN COMO POTENCIAS DE DOS")
    print("=" * 60)
    
    values = [1, 5, 10, 50, 100, 500, 1000, 5000]
    
    print("\n  Valor    → Exponente → Representación")
    print("  " + "-" * 40)
    
    for v in values:
        exp = value_to_exponent(v)
        approx = exponent_to_value(exp)
        error = abs(v - approx) / v * 100
        print(f"  {v:>6}   →    p={exp:>2}    → 2^{exp} = {approx:.0f} (error: {error:.1f}%)")


def demo_binomial_heap():
    """Demuestra operaciones de Binomial Heap."""
    print("\n" + "=" * 60)
    print("BINOMIAL HEAP - OPERACIONES")
    print("=" * 60)
    
    # Crear heap e insertar valores
    heap = BinomialHeap(level=0)
    values = [45, 23, 67, 12, 89, 34, 56, 78]
    
    print(f"\n  Insertando valores: {values}")
    for v in values:
        heap.insert(v)
    
    print(f"  Heap después de inserciones: {heap}")
    print(f"  Mínimo: {heap.get_min()}")
    print(f"  Distribución de exponentes: {heap.get_exponent_distribution()}")
    print(f"  Coherencia: {heap.compute_coherence():.3f}")
    
    # Demostrar SHIFT_LEFT
    print("\n  Aplicando SHIFT_LEFT (multiplicar por 2)...")
    heap.shift_left()
    print(f"  Nueva distribución: {heap.get_exponent_distribution()}")
    
    # Demostrar normalización
    print("\n  Insertando valores duplicados para demostrar normalización...")
    heap2 = BinomialHeap(level=0)
    for v in [100, 100, 100, 100]:  # 4 valores iguales
        heap2.insert(v)
    
    print(f"  Antes de normalizar: {heap2.get_exponent_distribution()}")
    heap2.normalize()
    print(f"  Después de normalizar: {heap2.get_exponent_distribution()}")


def demo_hierarchical_structure():
    """Demuestra la estructura jerárquica completa."""
    print("\n" + "=" * 60)
    print("ESTRUCTURA JERÁRQUICA")
    print("=" * 60)
    
    hierarchy = HierarchicalStructure(num_levels=4)
    
    # Simular latencias de diferentes magnitudes
    import random
    random.seed(42)
    
    # Valores pequeños (nivel 0)
    small_values = [random.gauss(10, 2) for _ in range(50)]
    # Valores medianos (nivel 1-2)
    medium_values = [random.gauss(100, 20) for _ in range(30)]
    # Valores grandes (nivel 2-3)
    large_values = [random.gauss(1000, 200) for _ in range(20)]
    
    all_values = small_values + medium_values + large_values
    random.shuffle(all_values)
    
    print(f"\n  Insertando {len(all_values)} valores...")
    for v in all_values:
        hierarchy.insert(max(1, v))  # Asegurar positivo
    
    print(f"\n  {hierarchy}")
    print(f"  Resonance Score Global: {hierarchy.compute_resonance_score():.3f}")
    
    print("\n  Análisis por nivel:")
    for level_data in hierarchy.get_level_analysis():
        print(f"    Nivel {level_data['level']}: "
              f"size={level_data['heap_size']}, "
              f"mean={level_data['mean']:.1f}, "
              f"coherence={level_data['coherence']:.3f}")


def demo_dvfs_controller():
    """Demuestra el controlador DVFS."""
    print("\n" + "=" * 60)
    print("CONTROLADOR DVFS")
    print("=" * 60)
    
    dvfs = DVFSController()
    
    print("\n  Simulando diferentes condiciones de carga:")
    print("  " + "-" * 50)
    
    scenarios = [
        (0.2, 0.1, "Carga baja, pocos rechazos"),
        (0.5, 0.3, "Carga media, rechazos moderados"),
        (0.8, 0.5, "Carga alta, muchos rechazos"),
        (0.9, 0.95, "Sobrecarga, casi todo rechazado"),
        (0.3, 0.1, "Recuperación"),
    ]
    
    for load, rejection, desc in scenarios:
        dvfs.update(load, rejection)
        stats = dvfs.get_stats()
        print(f"\n  {desc}:")
        print(f"    Load={load:.1f}, Rejection={rejection:.1f}")
        print(f"    → Freq={stats['frequency']:.3f}, "
              f"Volt={stats['voltage']:.3f}, "
              f"Energy={stats['energy']:.4f}")
        
        z_adj, cv_adj = dvfs.get_adjusted_thresholds(0.8, 0.95)
        print(f"    → Z-threshold: 0.80 → {z_adj:.3f}")
        print(f"    → CV-threshold: 0.95 → {cv_adj:.3f}")


def demo_complete_filter():
    """Demuestra el filtro completo."""
    print("\n" + "=" * 60)
    print("FILTRO TERMODINÁMICO VESELOV - DEMO COMPLETA")
    print("=" * 60)
    
    tpf = VeselovThermodynamicFilter(num_levels=4)
    
    import random
    random.seed(42)
    
    # Fase 1: Calibración
    print("\n  FASE 1: Calibración")
    print("  " + "-" * 40)
    
    for i in range(100):
        value = random.gauss(50, 10)
        tpf.update(max(1, value))
    
    print(f"  Calibrado: {tpf.calibrated}")
    print(f"  Media: {tpf.mean:.2f} ms")
    print(f"  Std: {tpf.std:.2f} ms")
    
    # Fase 2: Evaluación de diferentes shares
    print("\n  FASE 2: Evaluación de Shares")
    print("  " + "-" * 40)
    
    test_cases = [
        (40, "Rápido (bueno)"),
        (50, "Normal"),
        (65, "Lento"),
        (80, "Muy lento"),
        (35, "Muy rápido"),
    ]
    
    for value, desc in test_cases:
        # Actualizar filtro
        tpf.update(value)
        # Evaluar
        result = tpf.evaluate(value)
        
        print(f"\n  {desc} (latencia={value}ms):")
        print(f"    Decisión: {result.decision}")
        print(f"    Z-score: {result.z_score:+.2f}")
        print(f"    Nivel: {result.hierarchy_level}")
        print(f"    Resonancia: {result.resonance_score:.3f}")
        print(f"    Coherencia: {result.coherence:.3f}")
    
    # Estadísticas finales
    print("\n  ESTADÍSTICAS FINALES")
    print("  " + "-" * 40)
    stats = tpf.get_stats()
    print(f"  Total evaluados: {stats['total_evaluated']}")
    print(f"  Pasados: {stats['total_passed']} ({stats['pass_rate']*100:.1f}%)")
    print(f"  Filtrados: {stats['total_filtered']} ({stats['filter_rate']*100:.1f}%)")
    print(f"  Resonancia global: {stats['resonance_score']:.3f}")


def main():
    """Ejecuta todas las demostraciones."""
    print("""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║           MATEMÁTICAS DE VESELOV PARA FILTRADO TERMODINÁMICO                      ║
║                                                                                   ║
║   Basado en papers del Veselov Research Group (Enero 2026)                        ║
║                                                                                   ║
║   Innovaciones:                                                                   ║
║   1. Representación Jerárquica con Crecimiento Exponencial                        ║
║   2. Binomial Heaps para Gestión de Componentes                                   ║
║   3. Representación como Arrays de Potencias de Dos                               ║
║   4. Control DVFS Adaptativo                                                      ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
    """)
    
    demo_level_sizes()
    demo_powers_of_two()
    demo_binomial_heap()
    demo_hierarchical_structure()
    demo_dvfs_controller()
    demo_complete_filter()
    
    print("\n" + "=" * 60)
    print("FIN DE LA DEMOSTRACIÓN")
    print("=" * 60)


if __name__ == "__main__":
    main()
