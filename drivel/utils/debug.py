import gc
import time
import traceback

def stacks():
    gc.collect()
    gc.collect()
    gt = [o for o in gc.get_objects() if type(o).__name__ == 'GreenThread']
    stacks = {}
    for i in gt:
        st = '\n'.join(traceback.format_stack(i.gr_frame))
        try:
            stacks[st] += 1
        except KeyError, e:
            stacks[st] = 1
    stacks = stacks.items()
    stacks.sort(key=lambda i:i[1], reverse=True)
    for s,v in stacks:
        print 'COUNT', v, '\n', s
        x = raw_input()
        if x == 'q':
            break

def gt_by_lastswitch():
    gc.collect()
    gc.collect()
    age = lambda o: time.time() - o._last_switch_out
    stack = lambda o: '\n'.join(traceback.format_stack(o.gr_frame))
    gt = [(age(o), stack(o)) for o in gc.get_objects() if type(o).__name__ == 'GreenThread' and 
        hasattr(o, '_last_switch_out')]
    gt.sort(reverse=True)
    return gt

