import re
import ast
import json
from functools import partial

TEST_CASE = 'print_numbers.txt'

with open(TEST_CASE, 'r') as f:
    tree = ast.parse(f.read())
  
def serialize_ast(node):
    if isinstance(node, list):
        return list(map(serialize_ast, node))
        
    if not isinstance(node, ast.AST):
        return node
        
    result = {'CLASS': type(node).__name__}
    for field in node._fields:
        result[field] = serialize_ast(getattr(node, field))
    return result

json_dump = json.dumps(serialize_ast(tree), indent=4, sort_keys=True)
noquotes = re.sub(r'"(.+)":', r'\1:', json_dump)
fancyclassnames = re.sub(r'{\s*CLASS\: "(.+)",?', r'{ --\1--', noquotes)


def get_unique_name(prefix='var'):
    if prefix not in get_unique_name.uniques:
        get_unique_name.uniques[prefix] = -1
    get_unique_name.uniques[prefix] += 1
    return '$$' + prefix + str(get_unique_name.uniques[prefix])
get_unique_name.uniques = {}


class ParsingState:
    def __init__(self, loop_vars=[], delayed_expansion=False, loopname=None):
        self.loop_vars = loop_vars
        self.delayed_expansion = delayed_expansion
        self.loopname = loopname
    def clone(self, **kwargs):
        if 'loop_vars' not in kwargs: kwargs['loop_vars'] = self.loop_vars
        if 'delayed_expansion' not in kwargs: kwargs['delayed_expansion'] = self.delayed_expansion
        if 'loopname' not in kwargs: kwargs['loopname'] = self.loopname
        return ParsingState(**kwargs)


def ast_to_bat(node, state=ParsingState(delayed_expansion=True)):
    if isinstance(node, list):
        # TODO: Insert prefices
        if len(node) == 0:
            return '', ''
        stmts, prefices = zip(*[ast_to_bat(el, state.clone()) for el in node])
        print(stmts, prefices)
        return '\n'.join(stmts), '\n'.join(p for p in prefices if p)

    if not isinstance(node, ast.AST):
        return str(node), ''
    
    if isinstance(node, ast.Num):
        return str(node.n), ''
        
    if isinstance(node, ast.Str):
        return str(node.s), ''
    
    if isinstance(node, ast.NameConstant):
        if node.value == True: return str(1), ''
        if node.value == False: return str(0), ''
        print('Something unusual: ', node.value)
        return str(node.value), ''
    
    if isinstance(node, ast.Name):
        if node.id in state.loop_vars:
            return '%%' + node.id, ''
        if state.delayed_expansion:
            return '!' + node.id + '!', ''
        else:
            return '%' + node.id + '%', ''
   
    # TODO: Detect parameter count, create out variables and return to out
    if isinstance(node, ast.Expr):
        # Standalone call, prepend prefices directly
        if isinstance(node.value, ast.Call):
            print('EXPR CALL')
            call = node.value
            prefices = []
            args = []
            for arg in call.args:
                arg_expr = ast_to_bat(arg, state.clone(delayed_expansion=True))
                args.append(arg_expr[0])
                if arg_expr[1]: prefices.append(arg_expr[1])
            if call.func.id == 'print':
                return '\n'.join(prefices) + '\necho ' + ' '.join(args), ''
            if call.func.id == 'batch':
                return '\n'.join(prefices) + '\n' + '\n'.join(args), ''
            else:
                return '\n'.join(prefices) + '\ncall :' + call.func.id + ' ' + ' '.join(args), ''
        elif isinstance(node, ast.Call):
            # Call inside of a statement, return prefices separately
            print('NESTED CALL')
            call = node.value
            prefices = []
            args = []
            for arg in call.args:
                arg_expr = ast_to_bat(arg, state.clone(delayed_expansion=True))
                args.append(arg_expr[0])
                if arg_expr[1]: prefices.append(arg_expr[1])
            if call.func.id == 'print':
                return 'echo ' + ' '.join(args), '\n'.join(prefices)
            else:
                return 'call :' + call.func.id + ' ' + ' '.join(args), '\n'.join(prefices)
                
    if isinstance(node, ast.Call):
        print('NAKED CALL')
        # Call inside of a statement, return prefices separately
        prefices = []
        args = []
        for arg in node.args:
            arg_expr = ast_to_bat(arg, state.clone(delayed_expansion=True))
            args.append(arg_expr[0])
            if arg_expr[1]: prefices.append(arg_expr[1])
        if node.func.id == 'print':
            return 'echo ' + ' '.join(args), '\n'.join(prefices)
        else:
            out_var_name = get_unique_name('out')
            out, out_prefix = ast_to_bat(ast.Name(id=out_var_name), state.clone())
            #return out, '\n'.join(prefices) + '\n' + 'call :' + node.func.id + ' ' + ' '.join(args) + ' ' + out_var_name
            if node.func.id == 'input':
                return out, '\n'.join(prefices) +  'set /p {1}={0}'.format(' '.join(args) if args else '', out_var_name)   
            if node.func.id == 'randint':
                lo = args[0] if len(args) > 1 else 0
                hi = args[1] if len(args) > 1 else args[0] if len(args) == 1 else 32768
                return out, '\n'.join(prefices) +  'set /a "{2}={0}+({1}-{0}+1)*!random!/32768"'.format(lo, hi, out_var_name)
            return out, '\n'.join(prefices) +  'call: {0} {1} {2}'.format(node.func.id, ' '.join(args), out_var_name)
    
    if isinstance(node, ast.UnaryOp):
        # TODO: Get rid of unnecessary buffer if we can write directly to out variable
        if isinstance(node.op, ast.Not):
            # TODO: More pythonic truthyness check? (Empty strings/lists/sets, numeric 0, False, '')
            arg, prefix = ast_to_bat(node.operand, state.clone())
            out_var_name = get_unique_name('out')
            out, out_prefix = ast_to_bat(ast.Name(id=out_var_name), state.clone())
            evaluation_prefices = [
                'IF NOT "{0}"=="0" set "{1}=0"'.format(arg, out_var_name),
                'IF "{0}"=="0" set "{1}=1"'.format(arg, out_var_name)
            ]
            return out, '\n'.join([prefix, out_prefix] + evaluation_prefices)
            
    if isinstance(node, ast.BoolOp):
        operands, operand_prefices = zip(*[ast_to_bat(operand, state.clone()) for operand in node.values])
        operands_perfix = '\n'.join(operand_prefices)
        
        out_var_name = get_unique_name('out')
        out, out_prefix = ast_to_bat(ast.Name(id=out_var_name), state.clone())
        
        if isinstance(node.op, ast.And):
            evaluation_prefix = 'set "{2}=0"\nIF NOT "{0}"=="0" IF NOT "{1}"=="0" set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.op, ast.Or):
            evaluation_prefix = 'set "{2}=0"\nIF NOT "{0}"=="0" set "{2}=1"\nIF NOT "{1}"=="0" set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        
        return out, '\n'.join([operands_perfix, out_prefix, evaluation_prefix])
    
    if isinstance(node, ast.Compare):
        operands, operand_prefices = zip(*[ast_to_bat(operand, state.clone()) for operand in (node.left,) + (node.comparators,)])
        operands_perfix = '\n'.join(operand_prefices)
        
        out_var_name = get_unique_name('out')
        out, out_prefix = ast_to_bat(ast.Name(id=out_var_name), state.clone())
        
        if isinstance(node.ops[0], ast.Gt):
            evaluation_prefix = 'set "{2}=0"\nIF {0} GTR {1} set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.ops[0], ast.GtE):
            evaluation_prefix = 'set "{2}=0"\nIF {0} GEQ {1} set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.ops[0], ast.Eq):
            evaluation_prefix = 'set "{2}=0"\nIF {0}=={1} set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.ops[0], ast.NotEq):
            evaluation_prefix = 'set "{2}=1"\nIF {0}=={1} set "{2}=0"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.ops[0], ast.LtE):
            evaluation_prefix = 'set "{2}=0"\nIF {0} LEQ {1} set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.ops[0], ast.Lt):
            evaluation_prefix = 'set "{2}=0"\nIF {0} LSS {1} set "{2}=1"'.format(operands[0], operands[1], out_var_name)
        return out, '\n'.join([operands_perfix, out_prefix, evaluation_prefix])
    
    # String concatenation
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and any((isinstance(val, ast.Call) and val.func.id == 'str') or isinstance(val, ast.Str) for val in (node.left, node.right)):
            values = [val.args if (isinstance(val, ast.Call) and val.func.id == 'str') else val for val in (node.left, node.right)]
            
            operands, operand_prefices = zip(*[ast_to_bat(operand, state.clone()) for operand in values])
            operands_perfix = '\n'.join(operand_prefices)
            
            out_var_name = get_unique_name('out')
            out, out_prefix = ast_to_bat(ast.Name(id=out_var_name), state.clone())
            
            evaluation_prefix = 'set "{2}={0}{1}"'.format(operands[0], operands[1], out_var_name)
            
            return out, '\n'.join([operands_perfix, out_prefix, evaluation_prefix])
            
    if isinstance(node, ast.BinOp):
        operands, operand_prefices = zip(*[ast_to_bat(operand, state.clone()) for operand in (node.left, node.right)])
        operands_perfix = '\n'.join(operand_prefices)
        
        out_var_name = get_unique_name('out')
        out, out_prefix = ast_to_bat(ast.Name(id=out_var_name), state.clone())
        
        if isinstance(node.op, ast.Add):
            evaluation_prefix = 'set /a "{2}={0}+{1}"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.op, ast.Sub):
            evaluation_prefix = 'set /a "{2}={0}-{1}"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.op, ast.Mult):
            evaluation_prefix = 'set /a "{2}={0}*{1}"'.format(operands[0], operands[1], out_var_name)
        if isinstance(node.op, ast.Div):
            evaluation_prefix = 'set /a "{2}={0}/{1}"'.format(operands[0], operands[1], out_var_name)
            
        return out, '\n'.join([operands_perfix, out_prefix, evaluation_prefix])

    if isinstance(node, ast.If):
        body, body_prefix = ast_to_bat(node.body, state.clone())
        cond_result, cond_prefix = ast_to_bat(node.test, state.clone())
        result = '\n'.join([cond_prefix, body_prefix]) + '\nIF NOT "{0}"=="0" (\n'.format(cond_result) + body + '\n)'
        if hasattr(node, 'orelse') and node.orelse:
            else_body, else_prefix = ast_to_bat(node.orelse, state.clone())
            result += ' ELSE ( IF "{0}"=="0" (\n'.format(cond_result)
            result += '\n' + else_prefix + '\n' + else_body
            result += '\n) )'
        return result, ''
    
    if isinstance(node, ast.For):
        # TODO: Support other functions, support k, v
        loopname = get_unique_name('for')
        body, body_prefix = ast_to_bat(node.body, state.clone(loop_vars=state.loop_vars + [node.target.id], loopname=loopname))
        if node.iter.func.id == 'range':
            args, arg_prefices = zip(*[ast_to_bat(arg, state.clone()) for arg in node.iter.args])
            args_prefix = '\n'.join(arg_prefices)
            if not 1 <= len(args) <= 3:
                raise Exception('Range must receive 1 to 3 arguments, 0 given')
            elif len(args) == 1:
                args = (0,) + args + (1,)
            elif len(args) == 2:
                args = args + (1,)
            start, end, step = args
            iterator_name = node.target.id
            lines = [
                'FOR /L %%{0} IN ({1},{2},{3}) DO ('.format(iterator_name, start, step, end),
                body,
                ')\n:{0}'.format(loopname)
            ]
            return body_prefix + '\n' + args_prefix + '\n' + '\n'.join(lines), ''
        else:
            raise Exception('Only for ... in range(...) loops are supported!')
    
    if isinstance(node, ast.While):
        loopname = get_unique_name('while')
        body, body_prefix = ast_to_bat(node.body, state.clone(loopname=loopname))
        cond, cond_prefix = ast_to_bat(node.test, state.clone())
        return body_prefix + '\n:{0}\n{3}\nIF NOT "{1}"=="0" (\n{2}\ngoto :{0}\n)\n:{0}_end'.format(loopname, cond, body, cond_prefix), ''
    
    if isinstance(node, ast.Break):
        if state.loopname:
            return 'goto :{0}_end'.format(state.loopname), ''
        else:
            raise Exception('Break is only available inside a loop')
    
    if isinstance(node, ast.Assign):
        if isinstance(node.targets[0], ast.Tuple):
            ids = [el.id for el in node.targets[0].elts]
        else:
            ids = [node.targets[0].id]
        
        if hasattr(node.value, 'elts'):
            values = node.value.elts
        else:
            values = [node.value]
            
        values, value_prefices = zip(*[ast_to_bat(val, state.clone()) for val in values])
        values_prefix = '\n'.join(value_prefices)
        
        if len(ids) != len(values):
            raise Exception('Attempt to assign {0} values to {1} ids'.format(len(values), len(ids)))
        
        return values_prefix + '\n' + '\n'.join(['set "{0}={1}"'.format(*assignment) for assignment in zip(ids, values)]), ''
    
    if isinstance(node, ast.AugAssign):
        return ast_to_bat(
            ast.Assign(
                targets=[node.target],
                value=ast.BinOp(left=node.target, op=node.op, right=node.value)
            )
        , state.clone())
    
    stmts, prefices = ast_to_bat(node.body,  state.clone())
    return prefices + '\n' + stmts, ''

def strip_odd_linebreaks(text):
    return re.sub(r'\n+', r'\n', text)

def make_bat():
    result = strip_odd_linebreaks(ast_to_bat(tree)[0])
    result = '@echo off\nsetlocal ENABLEDELAYEDEXPANSION\n' + result
    with open('battest.bat', 'w') as f:
        f.write(result)
    print(result)

make_bat()
#print(fancyclassnames)