@tool
extends EditorPlugin
## Ponte com a Fornalha (Godot e Erethea Engine): a cada 2 segundos pergunta à
## Fornalha (só em 127.0.0.1) se ela gravou assets novos neste projeto; se
## gravou, o editor reimporta e recarrega as cenas abertas sozinho.

const ENDERECO := "http://127.0.0.1:11480/fornalha/ponte"
var _http: HTTPRequest
var _timer: Timer
var _versao := -1


func _enter_tree() -> void:
	_http = HTTPRequest.new()
	_http.timeout = 1.5
	add_child(_http)
	_http.request_completed.connect(_resposta)
	_timer = Timer.new()
	_timer.wait_time = 2.0
	_timer.autostart = true
	_timer.timeout.connect(_perguntar)
	add_child(_timer)


func _exit_tree() -> void:
	_timer.queue_free()
	_http.queue_free()


func _perguntar() -> void:
	if _http.get_http_client_status() == HTTPClient.STATUS_DISCONNECTED:
		var projeto := ProjectSettings.globalize_path("res://").uri_encode()
		_http.request("%s?projeto=%s" % [ENDERECO, projeto])


func _resposta(resultado: int, codigo: int, _cab: PackedStringArray, corpo: PackedByteArray) -> void:
	if resultado != HTTPRequest.RESULT_SUCCESS or codigo != 200:
		return
	var v = JSON.parse_string(corpo.get_string_from_utf8())
	if typeof(v) != TYPE_DICTIONARY:
		return
	var versao := int(v.get("versao", 0))
	if _versao != -1 and versao != _versao:
		print("Fornalha: assets novos (%s), reimportando..." % ", ".join(v.get("arquivos", [])))
		EditorInterface.get_resource_filesystem().scan()
		for cena in EditorInterface.get_open_scenes():
			EditorInterface.reload_scene_from_path(cena)
	_versao = versao
