import ast
import copy
import numbers
import typing as typ

class RewriteAssign(ast.NodeTransformer):
    # Rewrite cascade assignments to multiple simple assigns:
    # Example:
    # values = a, b = 123, 456
    # is converted to
    # values = 123, 456
    # a = [123, 456][0]
    # b = [123, 456][1]
    def visit_Assign(self, node):
        result = []
        for target_set in node.targets:
            if isinstance(target_set, ast.Tuple):
                target_set = target_set.elts
            else:
                target_set = [target_set]
            if len(target_set) == 1:
                result.append(ast.Assign(targets=[target_set[0]], value=node.value))
            elif len(target_set) > 1:
                for i, target in enumerate(target_set):
                    result.append(
                        ast.Assign(
                            targets=[target], 
                            value=ast.Subscript(
                                value=node.value, 
                                slice=ast.Index(value=ast.Num(n=i))
                              )
                        )
                    )
            else:
                raise Exception('Should not get here')
        return result

class RewriteSubscript(ast.NodeTransformer):
    # Rewrite literal subscripts to single values
    # Example:
    # [1, 2, 3][0]
    # is converted to
    # 1
    def visit_Subscript(self, node):
        super().generic_visit(node)
        if isinstance(node.value, ast.List) or isinstance(node.value, ast.Tuple):
            # TODO: Support slices
            if isinstance(node.slice, ast.Index):
                return node.value.elts[node.slice.value.n]
        # TODO: Support inline dicts
        return node
        
class RewriteForCollection(ast.NodeTransformer):
    def get_unique_iter_target(self):
        if not hasattr(RewriteForCollection.get_unique_iter_target, 'last_index'):
            setattr(RewriteForCollection.get_unique_iter_target, 'last_index', -1)
        RewriteForCollection.get_unique_iter_target.last_index += 1
        return '__iter' + str(RewriteForCollection.get_unique_iter_target.last_index)
        
    # Rewrtite for *targets in collection to for i in range(len(iterator))
    # Some non-literal collections are omitted (they are dealt with by batch code generator)
    def visit_For(self, node):
        super().generic_visit(node)
        # TODO: Support attributes
        if isinstance(node.iter, ast.Name) or ((isinstance(node.iter, ast.List) or isinstance(node.iter, ast.Tuple)) and not (all(isinstance(item, ast.Num) for item in node.iter.elts) or all(isinstance(item, ast.Str) for item in node.iter.elts))):
            targets = node.target.elts if hasattr(node.target, 'elts') else [node.target]
            indexator = self.get_unique_iter_target()
            set_targets = [
                ast.Assign(
                    targets=[t], 
                    value=ast.Subscript(
                        value=ast.Subscript(value=node.iter, slice=ast.Index(value=ast.Name(id=indexator))), 
                        slice=ast.Index(value=ast.Num(n=i))
                    )
                ) for i, t in enumerate(targets)
            ]
            
            return ast.For(
                target=indexator,
                iter=ast.Call(
                    func=ast.Name(id='range'),
                    args=[ast.Call(
                        func=ast.Name(id='len'),
                        args=node.iter
                    )]
                ),
                body=set_targets + node.body
            )
        return node

# Try to find an ast -> source function
try:
    import astunparse
    to_code = astunparse.unparse
except:
    try:
        import codegen
        to_code = codegen.to_source
    except:
        to_code = None

class EvaluateSimpleExprs(ast.NodeTransformer):
    def generic_visit(self, node):
        super().generic_visit(node)
        if not isinstance(node, ast.expr):
            return node
        if not to_code:
            return node
        # Try to eval the node in empty context
        try:
            result = eval(to_code(node), {}, {})
        except:
            return node
        # Try to parse the result back to ast
        try:
            evald_node = ast.parse(repr(result))
        except:
            return node
        return evald_node

# TODO: Implement this. Scopes.
'''
import copy
class AnnotateTypes(ast.NodeTransformer):
    def generic_visit(self, node):
        result = copy.deepcopy(node)
        result.type = None
        return result
    def visit_
'''

# Stores compile-time info about a given symbol (variable, function, class, etc)
# In particular, stores type constraints. Used for type inference
# Also may store some info for optimization
class SymbolInfo:
    def __init__(self, **kwargs):
        self.type_constraints = []
        for k, v in kwargs:
            setattr(self, k, v)
            
    def add_constraint(self, constraint):
        self.type_constraints.append(constraint)
        
    def add_constraints(self, constraints):
        for constraint in constraints:
            self.add_constraint(constraint)
            
    def get_constraints(self):
        return self.type_constraints

class Scope:
    def __init__(self, path):
        self.path = path
        self.symbols = dict()
    
    def getpath(self):
        return self.path
    
    def hassymbol(self, name):
        return name in self.symbols
    
    def getsymbol(self, name):
        return self.symbols[name]
    
    def setsymbol(self, name, value):
        if name in self.symbols:
            raise Exception('Attempt to redefine a symbol: %s' % name)
        self.symbols[name] = value
            
# Creates a SymbolInfo for all relevant nodes
# SymbolInfo is created for Names, ClassDefs and FunctionDefs
class AnnotateSymbolInfo:
    def __init__(self):
        super().__init__()
        self.scopes = [Scope('/')]
        
    # Move to a new empty scope
    # We must keep scope, othrwise variables with same name
    # will conflict even being declared e.g. in different functions
    def pushscope(self, name):
        self.scope.append(Scope(self.scopes[-1].getpath() + name + '/'))
    
    # Move back to previous scope
    # Current scope is discarded, but SymbolInfo objects
    # are kept bound to the corresponding AST nodes
    def popscope(self):
        self.scopes.pop()
    
    # Set a symbol info in current scope
    def setsymbol(self, name, value):
        self.scopes[-1].setsymbol(name, value)
    
    # Get symbol info from current scope
    def getsymbol(self, name):
        return self.scopes[-1].getsymbol(name)
    
    # Get symbol info from current or any parent scope
    def getsymbol_nonlocal(self, name):
        return next(scope.getsymbol(name) for scope in reversed(self.scopes) if scope.hassymbol(name))
    
    # Create SymbolInfo for a function, then visit its body
    def visit_FunctionDef(self, node):
        node = copy.deepcopy(node)
        self.setsymbol(node.name, SymbolInfo(name=node.name, type_constraints=[typ.Callable]))
        node.symbol_info = self.getsymbol(node.name)
        self.pushscope(name=node.name)
        self.generic_visit(node)
        self.popscope()
        return node
        
    def visit_AsyncFunctionDef(self, node):
        raise Exception('Async functions are not supported')
    
    # Create SymbolInfo for a class, then visit its body
    def visit_ClassDef(self, node):
        node = copy.deepcopy(node)
        # TODO: Probably classes need more than just Callable
        self.setsymbol(node.name, SymbolInfo(name=node.name, type_constraints=[typ.Callable]))
        node.symbol_info = self.getsymbol(node.name)
        self.pushscope(name=node.name)
        self.generic_visit(node)
        self.popscope()
        return node
    
    # Create SymbolInfo for a variable
    def visit_Name(self, node):
        node = copy.deepcopy(node)
        self.setsymbol(node.id, SymbolInfo(name=node.id))
        node.symbol_info = self.getsymbol(node.id)
        return node
        

def is_literal(node):
    if isinstance(node, (ast.Num, ast.Str, ast.NameConstant)):
        return True
    if hasattr(node, 'elts'):
        return all(is_literal(el) for el in node.elts)
    return False

# Infers type from literals or simple name assignments
def get_simple_expr_type_constarints(expr):
    if isinstance(expr, ast.Num):
        return [int] if isinstance(expr.n, numbers.Integral) else [float]
    elif isinstance(expr, ast.Str):
        return [str]
    elif isinstance(expr, ast.NameConstant) 
        if expr.value in ['True', 'False']:
            return [bool]
        elif expr.value == 'None':
            return [type(None)]
        else:
            raise Exception('Unknown name constant: %s' % expr.value)
    elif hasattr(expr, 'elts'):
        # ast.List -> typ.List, ast.Tuple -> typ.Tuple, etc
        type_constructor = getattr(typ, type(expr).__name__, None)
        if type_constructor:
            return type_constructor[*get_collection_node_types(expr.elts)]
        else:
            raise Exception('Unsupported collection type: %s' % type(expr).__name__)
    elif isinstance(expr, ast.Name):
        if hasattr(expr, 'symbol_info'):
            return expr.symbol_info.type_constraints
    return [typ.Any]

def get_collection_node_type_constraints(collection_node):
    type_constructor = getattr(typ, type(expr).__name__, None)
    if not type_constructor:
        type_constructor = typ.Container
    if len(collection_node.elts) == 0:
        return [type_constructor[typ.Any]]
    return [type_constructor[*list(set(get_simple_expr_type(el) for el in collection_node.elts))]]
    

class ConstrainLiteralAssign(ast.NodeTransformer):
    def visit_Assign(self, node):
        node = copy.deepcopy(node)
        constraints = get_simple_expr_type_constraints(node.value)
        node.targets[0].symbol_info.add_constraints(constraints)

# TODO: Annotate types for calls, literals, etc
# TODO: Constrain iterators

# TODO: Rewrite list, dict and tuple comprehensions    
# TODO: Rewrite IfExpr
def simplify_ast(node):
    result = node
    for transformer in [EvaluateSimpleExprs, RewriteAssign, RewriteSubscript, RewriteForCollection, EvaluateSimpleExprs]:
        result = transformer().visit(result)
    return result
    
def annotate_ast(node):
    result = node
    for transformer in [AnnotateSymbolInfo, AnnotateLiteralAssign]:
        result = transformer().visit(result)
    return result