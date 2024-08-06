package main

import (
	"context"
	"io"
	"log"
	"net"
	"os"
	"path/filepath"

	"BugBuster/SeedGenInj/internal/coverage"
	"BugBuster/SeedGenInj/internal/locate"
	"BugBuster/SeedGenInj/internal/runtime"
	"BugBuster/SeedGenInj/internal/viewcode"

	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
)

// global server state
type server struct {
	runtime.UnimplementedSeedGenServer
	lsc *locate.LocateServerComponent
}

func (s *server) Locate(ctx context.Context, req *runtime.LocateRequest) (*runtime.LocateResponse, error) {
	return locate.Locate(ctx, req, s.lsc)
}

func (s *server) View(ctx context.Context, req *runtime.ViewRequest) (*runtime.ViewResponse, error) {
	return viewcode.ViewCode(ctx, req)
}

func (s *server) Share(ctx context.Context, req *runtime.ShareRequest) (*runtime.ShareResponse, error) {
	filename := req.GetFilename()

	file, err := os.Open(filename)
	if err != nil {
		return &runtime.ShareResponse{Success: false}, err
	}

	defer file.Close()

	// copy the file to the shared directory, rename it to the hash of the file
	sharedDir := "/shared"
	fileId := uuid.New().String()
	sharedFilename := fileId + filepath.Ext(filename)
	sharedPath := sharedDir + sharedFilename

	sharedFile, err := os.Create(sharedPath)
	if err != nil {
		return &runtime.ShareResponse{Success: false}, err
	}

	defer sharedFile.Close()

	_, err = io.Copy(sharedFile, file)
	if err != nil {
		return &runtime.ShareResponse{Success: false}, err
	}

	return &runtime.ShareResponse{Success: true, Filename: sharedFilename}, nil
}

func (s *server) Run(ctx context.Context, req *runtime.RunRequest) (*runtime.RunResponse, error) {
	return coverage.GetCoverage(ctx, req, s.lsc)
}

func main() {
	lis, err := net.Listen("tcp", ":9002")
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	runtime.RegisterSeedGenServer(grpcServer, &server{lsc: locate.NewLocateServerComponent()})

	log.Println("[+] Seedgen-injected is running on port :9002")

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("seedgen-injected", grpc_health_v1.HealthCheckResponse_SERVING)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
