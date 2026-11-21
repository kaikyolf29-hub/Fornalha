# Removedor de fundo de mentira, com a mesma assinatura do trellis2.pipelines.rembg.BiRefNet.
class BiRefNet:
    def __init__(self, model_name: str = "ZhengPeng7/BiRefNet"):
        if "rmbg" in model_name.lower() or "briaai" in model_name.lower():
            raise RuntimeError(f"carregou {model_name}: licença não comercial (CC BY-NC 4.0)")
        self.model_name = model_name
