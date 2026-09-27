"""Frozen console entrypoint. MCP stdout stays strictly JSON-RPC."""
import json
import sys
from server import main,dispatch,VERSION
from studio_engine import StudioEngine

def doctor():
    import pythoncom
    import pywintypes
    import win32com.client
    result={'product':'cell_ppt_edited','version':VERSION,'windows':sys.platform=='win32','bundled_runtime':bool(getattr(sys,'frozen',False)),'pywin32':True}
    try:
        pywintypes.IID('PowerPoint.Application')
        result['powerpoint_registered']=True
    except pythoncom.com_error:
        result['powerpoint_registered']=False
    print(json.dumps(result))
    return 0 if result['windows'] and result['powerpoint_registered'] else 1

def self_test():
    e=StudioEngine()
    try:
        init=dispatch(e,{'jsonrpc':'2.0','id':1,'method':'initialize'})
        caps=e.capabilities()
        assert len(caps['actions'])==7
        assert '感谢抖音：木纹' in init['result']['instructions']
        import pythoncom,win32com.client
        print(json.dumps({'self_test':'passed','version':VERSION,'actions':len(caps['actions']),'COM_imports':True}))
        return 0
    finally:e.shutdown()

if __name__=='__main__':
    if len(sys.argv)==1:main()
    elif sys.argv[1:] == ['--doctor']:sys.exit(doctor())
    elif sys.argv[1:] == ['--self-test']:sys.exit(self_test())
    else:
        print('Usage: cell-ppt-edited.exe [--doctor|--self-test]',file=sys.stderr)
        sys.exit(2)
