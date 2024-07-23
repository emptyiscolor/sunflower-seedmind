package locate

import (
	"BugBuster/SeedGenInj/internal/runtime"
	"context"
	"log"
)

type LocateServerComponent struct {
	nmCache         *NMCache
	symbolizerCache map[string]*SymbolizerServer
}

func NewLocateServerComponent() *LocateServerComponent {
	return &LocateServerComponent{
		nmCache:         NewNMCache(),
		symbolizerCache: make(map[string]*SymbolizerServer),
	}
}

func LocateHarness(ctx context.Context, binary string, lsc *LocateServerComponent) (string, error) {
	functionAddress, err := lsc.nmCache.GetFunctionAddress(binary, "LLVMFuzzerTestOneInput")
	if err != nil {
		log.Println("Failed to get function address")
		return "", err
	}
	log.Printf("[+] Find LLVMFuzzerTestOneInput address: %s\n", functionAddress)
	symbolizer, exists := lsc.symbolizerCache[binary]
	if !exists {
		symbolizer, err = NewSymbolizerServer(binary)
		if err != nil {
			log.Println("Failed to create symbolizer server")
			return "", err
		}
		lsc.symbolizerCache[binary] = symbolizer
	}
	path, row, col, err := symbolizer.Symbolize(functionAddress)
	log.Printf("[+] Find LLVMFuzzerTestOneInput location: %s:%d:%d\n", path, row, col)
	return path, err
}

func Locate(ctx context.Context, req *runtime.LocateRequest, lsc *LocateServerComponent) (*runtime.LocateResponse, error) {

	log.Printf("[+] Locate request: %v\n", req)

	binary := "/" + req.GetHarnessBinary()
	functionName := req.GetFunctionName()

	functionAddress, err := lsc.nmCache.GetFunctionAddress(binary, functionName)
	if err != nil {
		log.Println("Failed to get function address")
		return &runtime.LocateResponse{Success: false}, err
	}

	log.Printf("[+] Find function %s address: %s\n", functionName, functionAddress)

	symbolizer, exists := lsc.symbolizerCache[binary]
	if !exists {
		symbolizer, err = NewSymbolizerServer(binary)
		if err != nil {
			log.Println("Failed to create symbolizer server")
			return &runtime.LocateResponse{Success: false}, err
		}
		lsc.symbolizerCache[binary] = symbolizer
	}

	path, line, col, err := symbolizer.Symbolize(functionAddress)

	log.Printf("[+] Find function %s location: %s:%d:%d\n", functionName, path, line, col)

	if err != nil {
		log.Println("Failed to symbolize")
		return &runtime.LocateResponse{Success: false}, err
	}

	return &runtime.LocateResponse{
		Success:  true,
		Filename: path,
		Line:     uint32(line),
	}, nil
}
