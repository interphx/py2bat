import ast

import .util

class Computation:
	def __init__(self, value, computation=[], is_ref=False):
		self.value = value
		self.computation = computation
		self.is_ref = is_ref

	def result(self, state):
		if self.is_ref:
			return self.value
		return util.expand_var(self.value, state)

class SymbolData:
	def __init__(self, name, type):
		self.name = name
		self.type = type
		
class Translator:
	def __init__(self, state):
		self.state_stack = []
		self.pushstate(state)
	def pushstate(state):
		self.state_stack.append(state)
	def popstate():
		return self.state_stack.pop(0)
	def get_symbol(name):
		for state in reversed(self.state_stack):
			if name in state.symbols:
				return state.symbols[name]
		return None
	def set_symbol(name, data):
		if name in self.states[-1].symbols:
			raise Exception('Attempt to redefine a symbol: {name}'.format(name))
		self.states[-1].symbols[name] = data
	
	def translate(node):
		if isinstance(node, ast.stmt):
			return self.translate_statement(node)
		elif isinstance(node, ast.expr):
			return self.translate_expression(node)

class BaseVisitor(ast.NodeVisitor):
    pass

class BatchWriter(BaseVisitor):
    def __init__(self):
        self.access_path = []
        self.lines = []
    
    def visit(self, node):
        self.access_path.append(node)
        return super().visit(node)
    
    def visit_Assign