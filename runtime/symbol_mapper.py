"""
runtime/symbol_mapper.py
Symbol Mapper for broker symbol normalization.
"""

class SymbolMapper:
    """
    Handles normalization of broker-specific symbol strings.
    """

    @staticmethod
    def normalize(broker_symbol: str) -> str:
        """
        Normalizes broker symbol names to standard canonical symbols.
        Example: XAUUSD.a -> XAUUSD, XAUUSDm -> XAUUSD, GOLDmicro -> XAUUSD
        """
        if not broker_symbol:
            return "UNKNOWN"
        
        sym = str(broker_symbol).strip().upper()
        
        # Gold variants
        if "GOLD" in sym or "XAU" in sym:
            return "XAUUSD"
        
        # Silver variants
        if "SILVER" in sym or "XAG" in sym:
            return "XAGUSD"
            
        # Common Forex major suffix stripping (e.g. EURUSD.a, EURUSDm, EURUSDecn)
        # Suffix list
        suffixes = [".A", ".M", "M", "A", "MICRO", "PRO", "ECN", "_ECN", ".ECN", ".PRO"]
        for suffix in suffixes:
            if sym.endswith(suffix):
                # Only strip if it leaves a standard canonical symbol (4 to 7 characters)
                cand = sym[:-len(suffix)]
                if 4 <= len(cand) <= 7:
                    sym = cand
                    break
                    
        return sym
