# ipop-project
# Copyright 2016, University of Florida
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


class CFxSubscription(object):
    def __init__(self, OwnerName, SubscriptionName):
        self.OwnerName = OwnerName
        self.Owner = None
        self.SubscriptionName = SubscriptionName
        self.subscribers = []

    '''
    sink must be an instance of a controller module
    '''

    def AddSubscriber(self, sink):

        self.subscribers.append(sink)

    def RemoveSubscriber(self, sink):
        pass

    def PostUpdate(self, msg):
        sink = None
        for sink in self.subscribers:
            self.Owner.registerCBT(sink.__class__.__name__, self.SubscriptionName, msg)
