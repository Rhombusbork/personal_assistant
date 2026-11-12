' 개인 비서 동기화를 창 없이 실행한다 (작업 스케줄러가 부름). 끝날 때까지 기다린다.
CreateObject("WScript.Shell").Run "wsl.exe -d Ubuntu -u neojun6007 -- /home/neojun6007/personal_assistant/bin/pa run --full", 0, True
