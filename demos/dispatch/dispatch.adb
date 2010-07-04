------------------------------------------------------------------------------
--                              Ada Web Server                              --
--                                                                          --
--                         Copyright (C) 2000-2003                          --
--                                ACT-Europe                                --
--                                                                          --
--  This library is free software; you can redistribute it and/or modify    --
--  it under the terms of the GNU General Public License as published by    --
--  the Free Software Foundation; either version 2 of the License, or (at   --
--  your option) any later version.                                         --
--                                                                          --
--  This library is distributed in the hope that it will be useful, but     --
--  WITHOUT ANY WARRANTY; without even the implied warranty of              --
--  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU       --
--  General Public License for more details.                                --
--                                                                          --
--  You should have received a copy of the GNU General Public License       --
--  along with this library; if not, write to the Free Software Foundation, --
--  Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.          --
--                                                                          --
--  As a special exception, if other files instantiate generics from this   --
--  unit, or you link this unit with other files to produce an executable,  --
--  this  unit  does not  by itself cause  the resulting executable to be   --
--  covered by the GNU General Public License. This exception does not      --
--  however invalidate any other reasons why the executable file  might be  --
--  covered by the  GNU Public License.                                     --
------------------------------------------------------------------------------

with Ada.Text_IO;

with AWS.Config;
with AWS.Server;
with AWS.Services.Dispatchers.URI;

with Dispatch_CB;

procedure Dispatch is

   use Ada;
   use AWS.Services;

   H  : AWS.Services.Dispatchers.URI.Handler;

   WS : AWS.Server.HTTP;

begin
   Text_IO.Put_Line ("AWS " & AWS.Version);
   Text_IO.Put_Line ("Enter 'q' key to exit...");

   Dispatchers.URI.Register (H, "/disp", Dispatch_CB.HW_CB'Access);

   AWS.Server.Start (WS, Dispatcher => H, Config => AWS.Config.Get_Current);

   --  Wait for 'q' key pressed...

   AWS.Server.Wait (AWS.Server.Q_Key_Pressed);

   --  Close servers.

   AWS.Server.Shutdown (WS);
end Dispatch;