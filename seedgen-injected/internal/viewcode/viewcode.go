package viewcode

import (
	"BugBuster/SeedGenInj/internal/runtime"
	"context"
	"log"
	"os"
)

func ViewCode(ctx context.Context, req *runtime.ViewRequest) (*runtime.ViewResponse, error) {
	filename := req.Filename

	file, err := os.Open(filename)
	if err != nil {
		log.Printf("Failed to open file %s: %v\n", filename, err)
		return &runtime.ViewResponse{Success: false}, err
	}
	defer file.Close()

	// read the file to a string "source"
	fileInfo, err := file.Stat()
	if err != nil {
		log.Printf("Failed to get file info for %s: %v\n", filename, err)
		return &runtime.ViewResponse{Success: false}, err
	}

	fileSize := fileInfo.Size()
	buffer := make([]byte, fileSize)

	_, err = file.Read(buffer)
	if err != nil {
		log.Printf("Failed to read file %s: %v\n", filename, err)
		return &runtime.ViewResponse{Success: false}, err
	}

	source := string(buffer)
	return &runtime.ViewResponse{Success: true, Source: source}, nil
}
