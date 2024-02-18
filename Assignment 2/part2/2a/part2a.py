import os
import torch
import numpy as np
from torchvision import datasets, transforms
import torch.optim as optim
from datetime import datetime
import model as mdl
import argparse
import torch.distributed as dist
from torch.utils.data.distributed import DistributedSampler
from torch.nn.parallel import DistributedDataParallel as DDP
device = "cpu"
torch.set_num_threads(4)

batch_size = 64 
def train_model(model, train_loader, optimizer, criterion, epoch):
    """
    model (torch.nn.module): The model created to train
    train_loader (pytorch data loader): Training data loader
    optimizer (optimizer.*): A instance of some sort of optimizer, usually SGD
    criterion (nn.CrossEntropyLoss) : Loss function used to train the network
    epoch (int): Current epoch number
    """

    # remember to exit the train loop at end of the epoch
    print("inside train")
    for batch_idx, (data, target) in enumerate(train_loader):
        # Your code goes here!
        if batch_idx == 1:
            starttime = datetime.now()
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        train_loss = criterion(output, target)
        train_loss.backward()
        for p in model.parameters():
            grad_list = [torch.zeros_like(p.grad) for _ in range(4)]
            dist.gather(p.grad, grad_list, group=None, async_op=False)
            grad_sum = torch.zeros_like(p.grad)
            for i in range(4):
                grad_sum += grad_list[i]
            grad_mean = grad_sum / 4
            scatter_list = [grad_mean for _ in range(4)]
            dist.scatter(p.grad, scatter_list, group=None, src=0, async_op=False)
            
            # group = dist.new_group([0, 1, 2, 3])
            print('Result gathered',dist.lst_of_gradients,type(dist.lst_of_gradients))
        optimizer.step()
        if batch_idx % 20 == 0:
            print("Iteration Number: ", batch_idx, ", loss: ", train_loss.item())
        if batch_idx == 195:
            endtime = datetime.now()
            print("Average time: ", (endtime - starttime).total_seconds()/195)

    return None

def test_model(model, test_loader, criterion):
    print("inside test")
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for batch_idx, (data, target) in enumerate(test_loader):
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += criterion(output, target)
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader)
    print('Test set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
            test_loss, correct, len(test_loader.dataset),
            100. * correct / len(test_loader.dataset)))
            

def main():
    print("inside main")
    parser = argparse.ArgumentParser()
    parser.add_argument('--master-ip', dest='master_ip', type=str, help='172.18.0.2')
    parser.add_argument('--num-nodes', dest='size', type=int, help='4')
    parser.add_argument('--rank', dest='rank', type=int, help='0')
    args = parser.parse_args()

    os.environ['MASTER_ADDR'] = args.master_ip
    os.environ['MASTER_PORT'] = '6585'
    dist.init_process_group('gloo', rank=args.rank, world_size=args.size)
    print(args.rank)
    torch.manual_seed(744)
    np.random.seed(744)

    normalize = transforms.Normalize(mean=[x/255.0 for x in [125.3, 123.0, 113.9]],
                                std=[x/255.0 for x in [63.0, 62.1, 66.7]])
    transform_train = transforms.Compose([
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            normalize,
            ])

    transform_test = transforms.Compose([
            transforms.ToTensor(),
            normalize])
    training_set = datasets.CIFAR10(root="./data", train=True,
                                                download=True, transform=transform_train)
    
    sampler_d = DistributedSampler(training_set) if torch.distributed.is_available() else None
    train_loader = torch.utils.data.DataLoader(training_set,
                                                    num_workers=2,
                                                    batch_size=batch_size,
                                                    sampler=sampler_d,
                                                    pin_memory=True)
    test_set = datasets.CIFAR10(root="./data", train=False,
                                download=True, transform=transform_test)

    test_loader = torch.utils.data.DataLoader(test_set,
                                              num_workers=2,
                                              batch_size=batch_size,
                                              shuffle=False,
                                              pin_memory=True)
    training_criterion = torch.nn.CrossEntropyLoss().to(device)

    model = mdl.VGG11()
    model.to(device)
   
    #model = DDP(model)
    
    optimizer = optim.SGD(model.parameters(), lr=0.1,
                          momentum=0.9, weight_decay=0.0001)
    # running training for one epoch
    for epoch in range(1):
        train_model(model, train_loader, optimizer, training_criterion, epoch)
        test_model(model, test_loader, training_criterion)

if __name__ == "__main__":
    main()
