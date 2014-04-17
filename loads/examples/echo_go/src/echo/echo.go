/* EchoServer
 */
package main

import (
	"code.google.com/p/go.net/websocket"
	"fmt"
	"io"
	"net/http"
)

var ActiveClients int = 0
var MaxClients int = 0

func closeSocket(ws *websocket.Conn) {
	ws.Close()
	ActiveClients -= 1
}

func Echo(ws *websocket.Conn) {
	ActiveClients += 1

	if ActiveClients > MaxClients {
		MaxClients = ActiveClients
	}

	defer closeSocket(ws)
	io.Copy(ws, ws)
}

func StatusHandler(resp http.ResponseWriter, req *http.Request) {
	reply := fmt.Sprintf("{\"max\":%d,\"active\":%d}", MaxClients, ActiveClients)
	resp.Write([]byte(reply))
}

func main() {
	// root page, displays the max number of sockets
	http.HandleFunc("/", StatusHandler)

	// web socket
	http.Handle("/ws", websocket.Handler(Echo))
	fmt.Println("Listening on port 9000")
	err := http.ListenAndServe(":9000", nil)
	if err != nil {
		panic("ListenAndServe: " + err.Error())
	}
}
