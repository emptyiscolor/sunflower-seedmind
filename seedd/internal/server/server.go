package server

import (
	"BugBuster/SeedD/internal/runtime"
	"context"
	"log"
	"net"

	"google.golang.org/grpc"
	_ "google.golang.org/grpc/encoding/gzip"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"

	"BugBuster/SeedD/internal/service"
)

const PORT = ":9002"

type server struct {
	runtime.UnimplementedSeedDServer
	runSeedsService        *service.RunSeedsService
	getRegionSourceService *service.GetRegionSourceService
	getFunctionsService    *service.GetFunctionsService
}

func newServer() *server {
	return &server{
		runSeedsService:        service.NewRunSeedsService(),
		getRegionSourceService: service.NewGetRegionSourceService(),
		getFunctionsService:    service.NewGetFunctionsService(),
	}
}

// RunSeeds delegates to the RunSeedsService
func (s *server) RunSeeds(ctx context.Context, req *runtime.RunSeedsRequest) (*runtime.RunSeedsResponse, error) {
	return s.runSeedsService.RunSeeds(ctx, req)
}

func (s *server) GetRegionSource(ctx context.Context, req *runtime.GetRegionSourceRequest) (*runtime.GetRegionSourceResponse, error) {
	return s.getRegionSourceService.GetRegionSource(ctx, req)
}

func (s *server) GetCallGraph(ctx context.Context, req *runtime.GetCallGraphRequest) (*runtime.GetCallGraphResponse, error) {
	return s.runSeedsService.GetCallGraph(ctx, req)
}

// UNIMPLEMENTED
// func (s *server) ExtractFunctionSource(ctx context.Context, req *runtime.ExtractFunctionSourceRequest) (*runtime.ExtractFunctionSourceResponse, error) {
// 	return nil, nil
// }

func (s *server) GetFunctions(ctx context.Context, req *runtime.GetFunctionsRequest) (*runtime.GetFunctionsResponse, error) {
	return s.getFunctionsService.GetFunctions(ctx, req)
}

func Serve() {
	lis, err := net.Listen("tcp", PORT)
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(1024*1024*1024),
		grpc.MaxSendMsgSize(1024*1024*1024),
	)

	runtime.RegisterSeedDServer(grpcServer, newServer())

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("seedd", grpc_health_v1.HealthCheckResponse_SERVING)

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
