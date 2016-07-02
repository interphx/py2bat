def expand_var(varname, state):
    if varname in state.batch.for_loop_vars:
        if len(varname) > 1:
            raise Exception('A for-loop var must be a single letter')
        return '%%' + varname

    if state.batch.expansion_level == 1:
        return '!' + varname + '!'
    elif state.batch.expansion_level == 2:
        return '%' + varname + '%'
    
    raise Exception('Expansion is too deep: {0}'.format(state.batch.expansion_level))