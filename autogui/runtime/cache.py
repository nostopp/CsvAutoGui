def clear_runtime_caches() -> None:
    from ..flow.loader import clear_raw_flow_cache
    from ..scripting.runtime import clear_script_cache

    clear_raw_flow_cache()
    clear_script_cache()
